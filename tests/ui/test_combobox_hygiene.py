"""Test d'hygiène statique et anti-régression des ComboBox (ADR 0058).

Vérifie de manière déterministe et statique qu'aucun composant UI sous src/ankidraft/ui/
n'instancie directement QComboBox brut ni n'injecte de feuille de style locale
concurrente ciblant QComboBox ou ses sous-éléments (drop-down, popup).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

# Racine du dossier UI à auditer
UI_ROOT = Path(__file__).resolve().parents[2] / "src" / "ankidraft" / "ui"

# Fichiers exemptés légitimement (socle technique du Design System)
EXEMPTED_FILES = {
    # Socle de définition de StyledComboBox et de son filtre molette
    UI_ROOT / "components" / "inputs.py",
}


def _is_exempted(path: Path) -> bool:
    """Vérifie si le fichier fait partie du socle technique exempté."""
    # Le sous-dossier style_engine/ est l'unique source de vérité légitime du CSS
    if "style_engine" in path.parts:
        return True
    return path in EXEMPTED_FILES


def _get_ui_python_files() -> list[Path]:
    """Retourne la liste des fichiers Python de l'UI à auditer."""
    return sorted([p for p in UI_ROOT.rglob("*.py") if not _is_exempted(p)])


@pytest.mark.unit
def test_no_raw_qcombobox_instantiation_in_ui() -> None:
    """Garantit qu'aucun fichier UI n'instancie directement QComboBox() brut."""
    violations: list[str] = []
    py_files = _get_ui_python_files()
    assert py_files, "Aucun fichier UI trouvé pour l'audit statique."

    for file_path in py_files:
        try:
            tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
        except SyntaxError as err:
            violations.append(f"{file_path}: Erreur de syntaxe ({err})")
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                # Détection QComboBox(...)
                if isinstance(func, ast.Name) and func.id == "QComboBox":
                    violations.append(f"{file_path.relative_to(UI_ROOT)}:{node.lineno} : Instanciation directe de QComboBox()")
                # Détection QtWidgets.QComboBox(...)
                elif isinstance(func, ast.Attribute) and func.attr == "QComboBox":
                    violations.append(f"{file_path.relative_to(UI_ROOT)}:{node.lineno} : Instanciation directe de {func.attr}()")

    assert not violations, (
        f"Régression ADR 0058 : Des instanciations brutes de QComboBox ont été détectées ({len(violations)}). "
        f"Utilisez StyledComboBox depuis ankidraft.ui.components.inputs :\n" + "\n".join(f"  - {v}" for v in violations)
    )


@pytest.mark.unit
def test_no_raw_qcombobox_import_in_ui() -> None:
    """Garantit qu'aucun fichier UI n'importe directement QComboBox depuis PySide6.QtWidgets."""
    violations: list[str] = []
    py_files = _get_ui_python_files()

    for file_path in py_files:
        try:
            tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and "QtWidgets" in node.module:
                for alias in node.names:
                    if alias.name == "QComboBox":
                        violations.append(f"{file_path.relative_to(UI_ROOT)}:{node.lineno} : Import direct de QComboBox")

    assert not violations, (
        f"Régression ADR 0058 : Des imports directs de QComboBox ont été détectés ({len(violations)}). "
        f"Importez StyledComboBox depuis ankidraft.ui.components.inputs :\n" + "\n".join(f"  - {v}" for v in violations)
    )


@pytest.mark.unit
def test_no_concurrent_combobox_css_in_ui() -> None:
    """Garantit qu'aucun fichier UI n'injecte de CSS local concurrent ciblant QComboBox."""
    violations: list[str] = []
    py_files = _get_ui_python_files()

    # Regex détectant les sélecteurs QSS ciblant QComboBox
    css_combobox_regex = re.compile(
        r"""QComboBox\s*(?:::[a-zA-Z0-9_-]+|:[a-zA-Z0-9_-]+|\s*QAbstractItemView|\s*\{)""",
        re.MULTILINE,
    )

    for file_path in py_files:
        content = file_path.read_text(encoding="utf-8")
        matches = list(css_combobox_regex.finditer(content))
        for m in matches:
            # Calcul du numéro de ligne
            lineno = content[: m.start()].count("\n") + 1
            matched_snippet = m.group(0).strip().replace("\n", " ")
            violations.append(f"{file_path.relative_to(UI_ROOT)}:{lineno} : Règle CSS concurrente '{matched_snippet}'")

    assert not violations, (
        f"Régression ADR 0058 : Des règles CSS locales ciblant QComboBox ont été détectées ({len(violations)}). "
        f"Le style des ComboBox est exclusivement géré par StyleEngine :\n" + "\n".join(f"  - {v}" for v in violations)
    )

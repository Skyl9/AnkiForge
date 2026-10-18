"""Tests headless Qt des raccourcis clavier de Documents, Analyse et Modèles (ADR 0032, T4).

Couvre :
- Documents : Ctrl+O (importer), Ctrl+S (sauvegarder), Ctrl+N (nouvel album),
  Ctrl+Alt+P (délimiter), Ctrl+Alt+R (vectoriser), Ctrl+Alt+C (couverture),
  Ctrl+Entrée (forger le chapitre ciblé).
- Analyse : Ctrl+Entrée (analyser), Ctrl+Alt+R (réindexer), Ctrl+Alt+A (aligner),
  Ctrl+Alt+F (forger le fragment ciblé).
- Modèles : Ctrl+N (nouveau type), Ctrl+Shift+D (dupliquer), Ctrl+S (enregistrer),
  Ctrl+Entrée (rafraîchir aperçu), Ctrl+Alt+O / Ctrl+Alt+E (importer / exporter JSON).
- Isolation des vues : les raccourcis ne se déclenchent que dans la vue affichée
  (aucun geste fantôme).
- Absence totale de QShortcut orphelin dans les vues migrées.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from PySide6.QtGui import QShortcut

from ankiforge.ui.shortcuts import ShortcutId, ShortcutManager
from ankiforge.ui.views.analysis_view import AnalysisView
from ankiforge.ui.views.card_models_view import CardModelsView
from ankiforge.ui.views.documents_view import DocumentsView

pytestmark = pytest.mark.ui


# ── Tests DocumentsView ────────────────────────────────────────────────────────


def test_documents_view_no_orphan_shortcuts(qtbot: Any, mock_db: Any) -> None:
    """Vérifie que DocumentsView n'a aucun QShortcut orphelin et s'appuie sur ShortcutManager."""
    manager = ShortcutManager()
    view = DocumentsView(shortcut_manager=manager)
    qtbot.addWidget(view)

    all_shortcuts = view.findChildren(QShortcut)
    manager_shortcuts = [rec.shortcut for rec in manager._bindings]
    for sc in all_shortcuts:
        assert sc in manager_shortcuts, f"QShortcut orphelin détecté dans DocumentsView: {sc}"


def test_documents_view_shortcuts_bindings(qtbot: Any, mock_db: Any) -> None:
    """Vérifie les bindings déclaratifs de DocumentsView."""
    manager = ShortcutManager()
    view = DocumentsView(shortcut_manager=manager)
    qtbot.addWidget(view)
    manager.set_active_view(view)

    bound_ids = {rec.id for rec in manager._bindings if rec.target is view}

    expected_ids = {
        ShortcutId.DOCUMENTS_IMPORT_FILE,
        ShortcutId.DOCUMENTS_NEW_ALBUM,
        ShortcutId.DOCUMENTS_DELIMIT_SCOPE,
        ShortcutId.DOCUMENTS_VECTORIZE,
        ShortcutId.DOCUMENTS_TOGGLE_COVERAGE,
    }
    assert expected_ids.issubset(bound_ids), f"Raccourcis manquants sur DocumentsView: {expected_ids - bound_ids}"

    # Vérification des déclenchements
    with (
        patch.object(view, "_on_import_file") as mock_import,
        patch.object(view, "_on_new_album") as mock_album,
        patch.object(view, "_on_open_delimitation_dialog") as mock_delimit,
        patch.object(view, "_on_vectorize_rag") as mock_rag,
        patch.object(view, "_toggle_coverage_panel") as mock_cov,
    ):
        for rec in manager._bindings:
            if rec.target is view:
                rec.shortcut.activated.emit()

        mock_import.assert_called_once()
        mock_album.assert_called_once()
        mock_delimit.assert_called_once()
        mock_rag.assert_called_once()
        mock_cov.assert_called_once()


def test_documents_view_save_and_run_primary(qtbot: Any, mock_db: Any) -> None:
    """Vérifie le routage de Ctrl+S (sauvegarder) et Ctrl+Entrée (forger le chapitre)."""
    manager = ShortcutManager()
    view = DocumentsView(shortcut_manager=manager)
    qtbot.addWidget(view)

    with patch.object(view, "_on_save_document") as mock_save:
        view.save()
        mock_save.assert_called_once()

    with patch.object(view, "_on_forge_selected_chapter") as mock_forge:
        view.run_primary_action()
        mock_forge.assert_called_once()


# ── Tests AnalysisView ─────────────────────────────────────────────────────────


def test_analysis_view_no_orphan_shortcuts(qtbot: Any, mock_db: Any) -> None:
    """Vérifie que AnalysisView n'a aucun QShortcut orphelin."""
    manager = ShortcutManager()
    view = AnalysisView(shortcut_manager=manager)
    qtbot.addWidget(view)

    all_shortcuts = view.findChildren(QShortcut)
    manager_shortcuts = [rec.shortcut for rec in manager._bindings]
    for sc in all_shortcuts:
        assert sc in manager_shortcuts, f"QShortcut orphelin détecté dans AnalysisView: {sc}"


def test_analysis_view_shortcuts_bindings(qtbot: Any, mock_db: Any) -> None:
    """Vérifie les bindings déclaratifs de la vue Analyse."""
    manager = ShortcutManager()
    view = AnalysisView(shortcut_manager=manager)
    qtbot.addWidget(view)
    manager.set_active_view(view)

    bound_ids = {rec.id for rec in manager._bindings if rec.target is view}

    expected_ids = {
        ShortcutId.ANALYSIS_REINDEX,
        ShortcutId.ANALYSIS_ALIGN_SOURCES,
        ShortcutId.ANALYSIS_FORGE_FRAGMENT,
    }
    assert expected_ids.issubset(bound_ids), f"Raccourcis manquants sur AnalysisView: {expected_ids - bound_ids}"

    with (
        patch.object(view, "_on_reindex_sources") as mock_reindex,
        patch.object(view, "_on_align_sources") as mock_align,
        patch.object(view, "_on_forge_fragment") as mock_forge,
    ):
        for rec in manager._bindings:
            if rec.target is view:
                rec.shortcut.activated.emit()

        mock_reindex.assert_called_once()
        mock_align.assert_called_once()
        mock_forge.assert_called_once()


def test_analysis_view_run_primary_action(qtbot: Any, mock_db: Any) -> None:
    """Vérifie que run_primary_action déclenche l'analyse Wozniak."""
    manager = ShortcutManager()
    view = AnalysisView(shortcut_manager=manager)
    qtbot.addWidget(view)

    with patch.object(view, "_on_run_analysis") as mock_run:
        view.run_primary_action()
        mock_run.assert_called_once()


# ── Tests CardModelsView ───────────────────────────────────────────────────────


def test_card_models_view_no_orphan_shortcuts(qtbot: Any, mock_db: Any) -> None:
    """Vérifie que CardModelsView n'a aucun QShortcut orphelin."""
    manager = ShortcutManager()
    view = CardModelsView(shortcut_manager=manager)
    qtbot.addWidget(view)

    all_shortcuts = view.findChildren(QShortcut)
    manager_shortcuts = [rec.shortcut for rec in manager._bindings]
    for sc in all_shortcuts:
        assert sc in manager_shortcuts, f"QShortcut orphelin détecté dans CardModelsView: {sc}"


def test_card_models_view_shortcuts_bindings(qtbot: Any, mock_db: Any) -> None:
    """Vérifie les bindings déclaratifs de CardModelsView."""
    manager = ShortcutManager()
    view = CardModelsView(shortcut_manager=manager)
    qtbot.addWidget(view)
    manager.set_active_view(view)

    bound_ids = {rec.id for rec in manager._bindings if rec.target is view}

    expected_ids = {
        ShortcutId.MODELS_NEW_TYPE,
        ShortcutId.MODELS_DUPLICATE,
        ShortcutId.MODELS_IMPORT_JSON,
        ShortcutId.MODELS_EXPORT_JSON,
    }
    assert expected_ids.issubset(bound_ids), f"Raccourcis manquants sur CardModelsView: {expected_ids - bound_ids}"

    with (
        patch.object(view, "_on_new_model") as mock_new,
        patch.object(view, "_on_duplicate_model") as mock_dup,
        patch.object(view, "_on_import_json") as mock_imp,
        patch.object(view, "_on_export_json") as mock_exp,
    ):
        for rec in manager._bindings:
            if rec.target is view:
                rec.shortcut.activated.emit()

        mock_new.assert_called_once()
        mock_dup.assert_called_once()
        mock_imp.assert_called_once()
        mock_exp.assert_called_once()


def test_card_models_view_save_and_run_primary(qtbot: Any, mock_db: Any) -> None:
    """Vérifie que save() enregistre le modèle et run_primary_action() rafraîchit l'aperçu."""
    manager = ShortcutManager()
    view = CardModelsView(shortcut_manager=manager)
    qtbot.addWidget(view)

    with patch.object(view, "_on_save_model") as mock_save:
        view.save()
        mock_save.assert_called_once()

    with patch.object(view, "_update_preview") as mock_preview:
        view.run_primary_action()
        mock_preview.assert_called_once_with(immediate=True)


# ── Tests Isolation et Pas de Geste Fantôme ───────────────────────────────────


def test_view_isolation_and_no_ghost_gestures(qtbot: Any, mock_db: Any) -> None:
    """Vérifie que les séquences partagées (Ctrl+Alt+R, Ctrl+N) ne se déclenchent que dans la vue active."""
    manager = ShortcutManager()
    doc_view = DocumentsView(shortcut_manager=manager)
    analysis_view = AnalysisView(shortcut_manager=manager)
    models_view = CardModelsView(shortcut_manager=manager)

    qtbot.addWidget(doc_view)
    qtbot.addWidget(analysis_view)
    qtbot.addWidget(models_view)

    # 1. Quand DocumentsView est active
    manager.set_active_view(doc_view)

    doc_r = [rec.shortcut for rec in manager._bindings if rec.target is doc_view and rec.id == ShortcutId.DOCUMENTS_VECTORIZE][0]
    ana_r = [rec.shortcut for rec in manager._bindings if rec.target is analysis_view and rec.id == ShortcutId.ANALYSIS_REINDEX][0]

    assert doc_r.isEnabled() is True
    assert ana_r.isEnabled() is False

    doc_n = [rec.shortcut for rec in manager._bindings if rec.target is doc_view and rec.id == ShortcutId.DOCUMENTS_NEW_ALBUM][0]
    mod_n = [rec.shortcut for rec in manager._bindings if rec.target is models_view and rec.id == ShortcutId.MODELS_NEW_TYPE][0]

    assert doc_n.isEnabled() is True
    assert mod_n.isEnabled() is False

    # 2. Quand AnalysisView devient active
    manager.set_active_view(analysis_view)
    assert doc_r.isEnabled() is False
    assert ana_r.isEnabled() is True
    assert doc_n.isEnabled() is False
    assert mod_n.isEnabled() is False

    # 3. Quand CardModelsView devient active
    manager.set_active_view(models_view)
    assert doc_r.isEnabled() is False
    assert ana_r.isEnabled() is False
    assert doc_n.isEnabled() is False
    assert mod_n.isEnabled() is True

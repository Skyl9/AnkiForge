"""Tests unitaires et d'interface graphique pour la Galerie de Test des Boîtes de Dialogue en Mode Dev.

Vérifie l'instanciation, le filtrage de recherche, l'intégration dans DeveloperTab et SettingsModal,
ainsi que l'isolation stricte par rapport à la base de données réelle (zéro écriture SQLite).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from PySide6.QtWidgets import QMessageBox

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionModel,
    PipelineRunModel,
)
from ankiforge.ui.dialogs.dialog_gallery_dialog import (
    DialogGalleryDialog,
    IsolatedBatchSliceComposerDialog,
    IsolatedCrashReportDialog,
    IsolatedGroupEditDialog,
    IsolatedTimeMachineDialog,
    build_mock_crash_report,
)
from ankiforge.ui.widgets.command_palette import CommandPalette
from ankiforge.ui.widgets.settings_modal import SettingsModal
from ankiforge.ui.widgets.settings_modal.tabs.developer_tab import DeveloperTab

pytestmark = pytest.mark.ui


@pytest.fixture(autouse=True)
def clean_db():
    """Garantit une base de données propre avant chaque test."""
    PipelineRunModel.delete().execute()
    CardModel.delete().execute()
    NoteVersionModel.delete().execute()
    NoteModel.delete().execute()
    NoteTypeModel.delete().execute()
    DeckModel.delete().execute()


def test_build_mock_crash_report():
    """Vérifie la génération d'un mock réaliste de CrashReport."""
    crash = build_mock_crash_report()
    assert crash is not None
    assert "ZeroDivisionError" in crash.traceback
    assert crash.active_profile == "dev"
    assert "mock_crash" in crash.fingerprint


def test_isolated_crash_report_dialog(qtbot):
    """Vérifie que le dialogue de crash report mocké fonctionne sans impacter QSettings."""
    dlg = IsolatedCrashReportDialog()
    qtbot.addWidget(dlg)
    assert dlg is not None
    assert dlg.crash_info is not None
    assert "ZeroDivisionError" in dlg.crash_info.traceback

    # Simuler le clic sur Ne pas redemander : neutralisé en mode galerie
    dlg.chk_dont_ask.setChecked(True)
    assert "Mode Galerie" in dlg.lbl_status.text()


def test_isolated_time_machine_dialog(qtbot):
    """Vérifie que la Time Machine mockée charge ses versions et n'écrit rien en BDD lors d'une restauration."""
    notes_count_before = NoteModel.select().count()
    versions_count_before = NoteVersionModel.select().count()

    dlg = IsolatedTimeMachineDialog()
    qtbot.addWidget(dlg)
    assert dlg is not None
    assert len(dlg.versions) == 3
    assert dlg.active_version is not None
    assert dlg.active_version.version_number == 3

    # Sélection de la version v1
    dlg.version_list.setCurrentRow(2)
    assert dlg.selected_version is not None
    assert dlg.selected_version.version_number == 1
    assert dlg.btn_restore.isEnabled() is True

    # Simulation de la restauration avec confirmation mockée
    with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
        dlg._restore_selected_version()

    # ZÉRO écriture en base de données réelle
    assert NoteModel.select().count() == notes_count_before
    assert NoteVersionModel.select().count() == versions_count_before


def test_isolated_group_edit_dialog(qtbot):
    """Vérifie que le dialogue d'édition groupée mocké simule l'opération sans toucher SQLite."""
    notes_count_before = NoteModel.select().count()

    dlg = IsolatedGroupEditDialog()
    qtbot.addWidget(dlg)
    assert dlg is not None
    assert len(dlg.note_ids) == 3

    fields = dlg._collect_available_fields()
    assert "Front" in fields
    assert "Back" in fields

    # Saisir un tag à ajouter et simuler l'application
    dlg.input_tags_add.setText("tag_simule")
    dlg._on_apply_clicked()

    assert dlg.result_data is not None
    assert dlg.result_data.success is True
    assert len(dlg.result_data.modified_note_ids) == 3

    # ZÉRO écriture en base de données réelle
    assert NoteModel.select().count() == notes_count_before


def test_isolated_batch_slice_composer_dialog(qtbot):
    """Vérifie que le découpeur de lot mocké s'ouvre et s'exécute sans insérer en file d'attente réelle."""
    runs_count_before = PipelineRunModel.select().count()

    dlg = IsolatedBatchSliceComposerDialog()
    qtbot.addWidget(dlg)
    assert dlg is not None
    assert dlg.body_stack.count() == 3

    # Accepter le dialogue ne crée aucun PipelineRunModel
    dlg.accept()
    assert PipelineRunModel.select().count() == runs_count_before


def test_dialog_gallery_dialog_ui_and_search(qtbot):
    """Vérifie la fenêtre de galerie des modales et le filtrage en direct."""
    gallery = DialogGalleryDialog()
    qtbot.addWidget(gallery)
    assert gallery is not None

    # Doit contenir au minimum les 6 dialogues du ticket
    assert len(gallery.dialog_cards) >= 6

    gallery.show()

    # Test du filtre par recherche
    gallery.search_input.setText("crash")
    visible_cards = [c for c in gallery.dialog_cards if not c.isHidden()]
    assert len(visible_cards) == 1
    assert "CrashReportDialog" in visible_cards[0].dialog_name

    # Réinitialisation du filtre
    gallery.search_input.clear()
    assert all(not c.isHidden() for c in gallery.dialog_cards)


def test_developer_tab_ui_and_launchers(qtbot):
    """Vérifie la présence des cartes d'environnement et de la galerie dans DeveloperTab."""
    tab = DeveloperTab()
    qtbot.addWidget(tab)
    assert tab is not None
    assert tab.lbl_env_name is not None
    assert len(tab.launcher_buttons) >= 6


def test_settings_modal_dev_tab_conditional(qtbot):
    """Vérifie que DeveloperTab n'est présent que lorsque is_development() est vrai."""
    # 1. En environnement standard (non-dev)
    with patch("ankiforge.ui.widgets.settings_modal.modal.is_development", return_value=False):
        modal_prod = SettingsModal()
        qtbot.addWidget(modal_prod)
        assert modal_prod.stacked_widget.count() == 9
        assert modal_prod.dev_tab is None

    # 2. En environnement de développement (--dev)
    with patch("ankiforge.ui.widgets.settings_modal.modal.is_development", return_value=True):
        modal_dev = SettingsModal()
        qtbot.addWidget(modal_dev)
        assert modal_dev.stacked_widget.count() == 10
        assert modal_dev.dev_tab is not None
        assert isinstance(modal_dev.dev_tab, DeveloperTab)


def test_command_palette_dev_command_conditional(qtbot):
    """Vérifie que la commande d'ouverture de la galerie n'apparaît qu'en mode dev dans la palette."""
    with patch("ankiforge.ui.widgets.command_palette.is_development", return_value=False):
        palette_prod = CommandPalette()
        qtbot.addWidget(palette_prod)
        cmd_ids_prod = [cmd["id"] for cmd in palette_prod.commands]
        assert "action.dialog_gallery" not in cmd_ids_prod

    with patch("ankiforge.ui.widgets.command_palette.is_development", return_value=True):
        palette_dev = CommandPalette()
        qtbot.addWidget(palette_dev)
        cmd_ids_dev = [cmd["id"] for cmd in palette_dev.commands]
        assert "action.dialog_gallery" in cmd_ids_dev


def test_main_window_open_dialog_gallery_conditional(qtbot):
    """Vérifie que MainWindow._open_dialog_gallery n'ouvre la galerie qu'en mode dev."""
    from ankiforge.ui.main_window import MainWindow

    main_win = MainWindow(ai_manager=None, profile_name="test")
    qtbot.addWidget(main_win)

    # 1. Non-dev : ne fait rien
    with patch("ankiforge.ui.main_window.is_development", return_value=False), patch("ankiforge.ui.dialogs.dialog_gallery_dialog.DialogGalleryDialog.exec") as mock_exec:
        main_win._open_dialog_gallery()
        mock_exec.assert_not_called()

    # 2. Dev : instancie et exécute DialogGalleryDialog
    with patch("ankiforge.ui.main_window.is_development", return_value=True), patch("ankiforge.ui.dialogs.dialog_gallery_dialog.DialogGalleryDialog.exec", return_value=0) as mock_exec:
        main_win._open_dialog_gallery()
        mock_exec.assert_called_once()

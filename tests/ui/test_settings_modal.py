"""
Tests unitaires et d'interface graphique (PySide6 / pytest-qt) pour SettingsModal et ses 5 onglets.
Vérifie la création, le basculement d'onglets, la persistance des préférences, les actions réelles de maintenance,
la validation des clés API, les règles de formats/fusion Anki hors-ligne et la réactivité au thème clair/sombre.
"""

import datetime
import json
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QMessageBox

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    LLMConfigModel,
    MediaModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionMediaModel,
    NoteVersionModel,
)
from ankiforge.services.settings_service import SettingsService
from ankiforge.ui.style_engine import get_style_engine
from ankiforge.ui.widgets.settings_modal import (
    AIEnginesTab,
    AnkiSyncTab,
    GeneralTab,
    PasswordLineEdit,
    SettingsModal,
    StorageMaintenanceTab,
)


@pytest.fixture(autouse=True)
def setup_settings_test_db():
    """Initialise une base propre pour chaque test de paramètres."""
    # Nettoyage
    LLMConfigModel.delete().execute()
    CardModel.delete().execute()
    NoteVersionMediaModel.delete().execute()
    NoteVersionModel.delete().execute()
    NoteModel.delete().execute()
    NoteTypeModel.delete().execute()
    DeckModel.delete().execute()
    MediaModel.delete().execute()

    # Données initiales
    nt = NoteTypeModel.create(name="Modèle Test", fields_schema='["Front", "Back"]')
    deck = DeckModel.create(name="Paquet Test")
    note = NoteModel.create(guid="guid-test-1", note_type=nt, tags="test")
    CardModel.create(note=note, deck=deck, template_index=0)


def test_settings_modal_creation_and_tabs(qtbot):
    """Vérifie l'instanciation complète de SettingsModal et la navigation dans les 5 onglets."""
    modal = SettingsModal()
    qtbot.addWidget(modal)
    assert modal is not None

    assert isinstance(modal.general_tab, GeneralTab)
    assert isinstance(modal.ai_tab, AIEnginesTab)
    assert isinstance(modal.anki_tab, AnkiSyncTab)
    assert isinstance(modal.maint_tab, StorageMaintenanceTab)
    assert modal.stacked_widget.count() == 5

    # Navigation dans tous les onglets
    for i in range(5):
        modal.stacked_widget.setCurrentIndex(i)
        assert modal.stacked_widget.currentIndex() == i


def test_general_tab_save_and_mode_change(qtbot):
    """Teste la modification et la sauvegarde des paramètres généraux."""
    tab = GeneralTab()
    qtbot.addWidget(tab)

    tab.cb_lang.setCurrentText("English")
    tab.cb_batch_style.setCurrentText("Kanban (Flux de tâches)")
    tab.le_export.setText("/custom/export/path")

    has_change, layout_id, theme_id = tab.save_tab()
    assert has_change is True
    assert SettingsService.get("ui/language") == "English"
    assert SettingsService.get("app/batch_factory_style") == "Kanban (Flux de tâches)"
    assert SettingsService.get("app/export_path") == "/custom/export/path"


def test_password_line_edit_toggle(qtbot):
    """Teste le widget PasswordLineEdit et son basculement d'affichage."""
    from PySide6.QtWidgets import QLineEdit

    pwd_edit = PasswordLineEdit(placeholder="sk-...", initial_text="secret_key_123")
    qtbot.addWidget(pwd_edit)

    assert pwd_edit.text() == "secret_key_123"
    assert pwd_edit.edit.echoMode() == QLineEdit.EchoMode.Password

    # Clic toggle -> visible
    pwd_edit.btn_toggle.click()
    assert pwd_edit.edit.echoMode() == QLineEdit.EchoMode.Normal

    # Clic toggle -> masqué
    pwd_edit.btn_toggle.click()
    assert pwd_edit.edit.echoMode() == QLineEdit.EchoMode.Password


def test_ai_engines_tab_key_validation_and_crud(qtbot):
    """Teste la validation de format de clé, l'ajout et la suppression d'un moteur IA."""
    tab = AIEnginesTab()
    qtbot.addWidget(tab)

    # 1. Validation de clé vide vs valide
    tab.key_edits["openai"].setText("")
    tab._test_cloud_key("openai", "OpenAI")
    assert tab.key_status_badges["openai"].text() == "⚠️ Clé vide"

    tab.key_edits["openai"].setText("sk-proj-1234567890abcdef1234567890")
    tab._test_cloud_key("openai", "OpenAI")
    assert tab.key_status_badges["openai"].text() == "✅ Format valide"

    # 2. Ajout rapide d'un moteur
    initial_count = LLMConfigModel.select().count()
    tab._quick_add_engine("Custom Test Model", "openai", "gpt-4o-custom", False)
    assert LLMConfigModel.select().count() == initial_count + 1

    # 3. Sauvegarde des clés
    tab.save_tab()
    assert SettingsService.get("keys/openai") == "sk-proj-1234567890abcdef1234567890"


def test_ai_engines_tab_ollama_scan_mocked(qtbot):
    """Teste le scan d'Ollama avec réponse simulée."""
    tab = AIEnginesTab()
    qtbot.addWidget(tab)

    fake_response = json.dumps({"models": [{"name": "llama3:latest"}, {"name": "mistral:latest"}]}).encode("utf-8")

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_cm = MagicMock()
        mock_cm.read.return_value = fake_response
        mock_cm.__enter__.return_value = mock_cm
        mock_urlopen.return_value = mock_cm

        tab._scan_ollama()

        assert "2 modèle(s) détecté(s)" in tab.badge_ollama_status.text()
        assert LLMConfigModel.select().where(LLMConfigModel.model_id == "llama3:latest").exists()


def test_anki_sync_tab_config_and_save(qtbot, tmp_path):
    """Teste la configuration des règles Smart Merge, formats de compression et répertoire Anki2."""
    tab = AnkiSyncTab()
    qtbot.addWidget(tab)

    # 1. Modification des politiques et compression
    tab.cb_conflict_policy.setCurrentIndex(1)  # "local"
    tab.chk_silent_merge.setChecked(False)
    tab.cb_compression.setCurrentIndex(1)  # "zip"

    custom_anki_dir = str(tmp_path / "CustomAnki2")
    tab.le_anki_dir.setText(custom_anki_dir)

    # 2. Sauvegarde
    tab.save_tab()

    assert SettingsService.get("anki/conflict_policy") == "local"
    assert SettingsService.get("anki/silent_meta_merge") is False
    assert SettingsService.get("anki/compression") == "zip"
    assert SettingsService.get("anki/collection_dir") == custom_anki_dir

    # 3. Test de parcours dossier
    with patch("PySide6.QtWidgets.QFileDialog.getExistingDirectory", return_value=str(tmp_path / "PickedAnki2")):
        tab._browse_anki_dir()
        assert tab.le_anki_dir.text() == str(tmp_path / "PickedAnki2")


def test_storage_maintenance_tab_actions(qtbot):
    """Teste les actions de maintenance (VACUUM, nettoyage orphelins, purge et snapshot)."""
    tab = StorageMaintenanceTab()
    qtbot.addWidget(tab)

    # 1. Refresh des métriques
    tab.refresh_metrics()
    assert "note" in tab.c_db.lbl_sub.text()

    # 2. VACUUM
    tab._run_vacuum()

    # 3. Nettoyage médias orphelins
    m = MediaModel.create(filename="orphan_test.png", original_name="test.png", checksum="abc123456", mime_type="image/png")
    assert MediaModel.select().where(MediaModel.id == m.id).exists()
    tab._clean_orphan_media()
    assert not MediaModel.select().where(MediaModel.id == m.id).exists()

    # 4. Purge Time Machine (Simulation réponse Oui)
    old_date = datetime.datetime.now() - datetime.timedelta(days=45)
    nv = NoteVersionModel.create(note=NoteModel.select().first(), version_number=1, snapshot_json="{}", created_at=old_date, is_active=False)
    with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
        tab._purge_history()
        assert not NoteVersionModel.select().where(NoteVersionModel.id == nv.id).exists()

    # 5. Snapshot Backup
    with patch("ankiforge.ui.widgets.settings_modal.backup_database") as mock_backup:
        tab._create_snapshot()
        mock_backup.assert_called_once()


def test_settings_modal_theme_reactivity(qtbot):
    """Vérifie que la modale et tous ses onglets supportent le rafraîchissement de thème sans exception."""
    modal = SettingsModal()
    qtbot.addWidget(modal)

    engine = get_style_engine()
    dark_prof = engine.get_theme("ide")
    light_prof = engine.get_theme("jetbrains_light")

    # Appliquer thème sombre
    modal.refresh_theme(dark_prof)
    assert modal.lbl_title.text() == "Paramètres AnkiForge"

    # Appliquer thème clair
    modal.refresh_theme(light_prof)
    assert modal.lbl_title.text() == "Paramètres AnkiForge"

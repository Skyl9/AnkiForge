"""
Tests unitaires et d'interface graphique (PySide6 / pytest-qt) pour SettingsModal et ses 5 onglets.
Vérifie la création, le basculement d'onglets, la persistance des préférences, les actions réelles de maintenance,
la validation des clés API, les règles de formats/fusion Anki hors-ligne et la réactivité au thème clair/sombre.
"""

import datetime
import json
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QLineEdit, QMessageBox

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
    TTSSettingsTab,
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
    assert isinstance(modal.tts_tab, TTSSettingsTab)
    assert isinstance(modal.maint_tab, StorageMaintenanceTab)
    assert modal.stacked_widget.count() == 6

    # Navigation dans tous les onglets
    for i in range(6):
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


def test_password_line_edit_replaces_previous_value_cleanly(qtbot):
    """Le remplacement d'une clé ne doit pas laisser de rendu résiduel dans le champ."""
    pwd_edit = PasswordLineEdit(initial_text="ancienne_cle")
    qtbot.addWidget(pwd_edit)

    pwd_edit.setText("nouvelle_cle")

    assert pwd_edit.text() == "nouvelle_cle"
    assert pwd_edit.edit.cursorPosition() == len("nouvelle_cle")


def test_ai_catalogue_inline_editor_has_opaque_background(qtbot):
    """L'éditeur inline du catalogue masque le texte de la cellule sous-jacente."""
    tab = AIEnginesTab()
    qtbot.addWidget(tab)
    assert tab.table_engines.verticalHeader().defaultSectionSize() == 34
    assert "height: 28px" in tab.table_engines.styleSheet()

    tab.table_engines.setRowCount(1)
    item = tab.table_engines.item(0, 0)
    if item is None:
        from PySide6.QtWidgets import QTableWidgetItem

        item = QTableWidgetItem("Ancien modèle")
        tab.table_engines.setItem(0, 0, item)

    tab.table_engines.editItem(item)
    qtbot.wait(20)
    editor = tab.table_engines.findChild(QLineEdit)

    assert editor is not None
    assert "QTableWidget QLineEdit" in tab.table_engines.styleSheet()


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


def test_ai_engines_tab_key_test_surfaces_save_failure_without_crashing(qtbot):
    """Le bouton de test ne doit pas faire tomber l'onglet si la persistance échoue."""
    tab = AIEnginesTab()
    qtbot.addWidget(tab)
    tab.key_edits["openai"].setText("sk-proj-1234567890abcdef1234567890")

    with patch.object(SettingsService, "set", side_effect=RuntimeError("database unavailable")), patch("ankiforge.ui.widgets.settings_modal.tabs.ai_engines_tab.show_toast") as toast:
        tab._test_cloud_key("openai", "OpenAI")

    toast.assert_called_once()
    assert "Impossible d'enregistrer" in toast.call_args.args[1]


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
    qtbot.waitUntil(lambda: tab._maintenance_worker is None, timeout=5000)
    assert tab.btn_vacuum.isEnabled()

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


def test_tts_settings_tab_actions(qtbot, tmp_path):
    """Vérifie le test de voix et les callbacks d'installation de Piper dans TTSSettingsTab."""
    tab = TTSSettingsTab()
    qtbot.addWidget(tab)

    fake_audio = tmp_path / "sample.mp3"
    fake_audio.write_bytes(b"fake mp3 audio data")

    with patch.object(tab.tts_service, "synthesize", return_value=("[sound:sample.mp3]", fake_audio)), patch.object(tab._player, "play") as mock_play:
        tab._on_test_voice()
        mock_play.assert_called_once()

    # Vérification des callbacks installateur sans exception
    tab._on_installer_success()
    assert "Piper installé avec succès" in tab.lbl_install_progress.text()

    tab._on_installer_failed("Réseau indisponible")
    assert "Échec du téléchargement" in tab.lbl_install_progress.text()


def test_ai_engines_tab_save_syncs_models_and_reloads_provider(qtbot):
    """Vérifie que la sauvegarde met à jour les LLMConfigModel en BDD et recharge l'AIManager."""
    mock_ai_manager = MagicMock()
    tab = AIEnginesTab(ai_manager=mock_ai_manager)
    qtbot.addWidget(tab)

    # Création préalable d'un modèle OpenAI en base sans clé
    cfg = LLMConfigModel.create(
        display_name="GPT-4o Test",
        provider="openai",
        model_id="gpt-4o",
        context_limit=128000,
        api_key="",
        is_free=False,
    )

    new_key = "sk-proj-updated-test-key-1234567890"
    tab.key_edits["openai"].setText(new_key)
    tab.save_tab()

    # Vérification BDD SettingModel et LLMConfigModel
    assert SettingsService.get("keys/openai") == new_key
    updated_cfg = LLMConfigModel.get_by_id(cfg.id)
    assert updated_cfg.api_key == new_key

    # Vérification notification reload_provider
    mock_ai_manager.reload_provider.assert_called()


def test_flexible_service_empty_credentials_fallback():
    """Vérifie que create_provider replie gracieusement sur MockProvider quand aucune clé n'est configurée."""
    from ankiforge.services.ai.base import MockProvider
    from ankiforge.services.ai.flexible_service import AIManager

    with patch("ankiforge.services.settings_service.SettingsService.get", return_value=""), patch.dict("os.environ", {}, clear=False):
        # Clé vide pour OpenAI -> MockProvider au lieu d'exception
        p_openai = AIManager.create_provider("openai", "gpt-4o", api_key="")
        assert isinstance(p_openai, MockProvider)

        # Clé vide pour Gemini -> MockProvider au lieu d'exception
        p_gemini = AIManager.create_provider("gemini", "gemini-2.5-flash", api_key="")
        assert isinstance(p_gemini, MockProvider)


def test_katex_editor_text_under_cursor_multiline(qtbot):
    """Vérifie que textUnderCursor ne lève pas IndexError sur un document multiligne."""
    from ankiforge.ui.widgets.katex_editor import KaTeXTextEdit

    editor = KaTeXTextEdit()
    qtbot.addWidget(editor)

    # Texte sur plusieurs lignes
    editor.setPlainText("Première ligne très longue de texte\nDeuxième ligne courte\n\\frac")

    # Placer le curseur à la fin du document (sur '\\frac')
    cursor = editor.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    editor.setTextCursor(cursor)

    # Doit renvoyer '\\frac' sans IndexError
    assert editor.textUnderCursor() == "\\frac"

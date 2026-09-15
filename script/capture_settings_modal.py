"""
Script de capture offscreen pour la modale Paramètres (SettingsModal).
Génère des captures pour tous les onglets (Général, Moteurs IA, Anki & Synchro, Stockage & Maintenance, Extensions)
en mode sombre et clair.
"""

import os
import sys

# Configurer Qt pour le mode headless offscreen
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QT_LOGGING_RULES"] = "*.debug=false;qt.qpa.*=false"

from PySide6.QtWidgets import QApplication

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    LLMConfigModel,
    MediaModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionMediaModel,
    NoteVersionModel,
    SettingModel,
    db,
)
from ankiforge.ui.style_engine import get_style_engine
from ankiforge.ui.widgets.settings_modal import SettingsModal


def seed_settings_data():
    models = [
        DeckModel,
        NoteTypeModel,
        NoteModel,
        CardModel,
        NoteVersionModel,
        MediaModel,
        NoteVersionMediaModel,
        LLMConfigModel,
        SettingModel,
    ]
    db.create_tables(models, safe=True)

    if DeckModel.select().count() == 0:
        DeckModel.create(name="Défaut", description="Paquet principal")
        DeckModel.create(name="Sciences::Physique", description="Physique moderne")

    if NoteTypeModel.select().count() == 0:
        NoteTypeModel.create(name="Basique", fields_schema='["Front", "Back"]')

    if NoteModel.select().count() == 0:
        nt = NoteTypeModel.select().first()
        dk = DeckModel.select().first()
        for i in range(5):
            n = NoteModel.create(guid=f"guid-demo-{i}", note_type=nt, tags="demo,paramètres")
            CardModel.create(note=n, deck=dk, template_index=0)
            NoteVersionModel.create(note=n, version_number=1, snapshot_json='{"Front": "Q", "Back": "R"}', is_active=True)

    if LLMConfigModel.select().count() == 0:
        LLMConfigModel.create(display_name="GPT-4o (OpenAI)", provider="openai", model_id="gpt-4o", context_limit=128000, api_key="sk-proj-123456789", is_free=False)
        LLMConfigModel.create(display_name="Claude 3.5 Sonnet", provider="anthropic", model_id="claude-3-5-sonnet-20241022", context_limit=200000, api_key="sk-ant-123456789", is_free=False)
        LLMConfigModel.create(display_name="Ollama Local (Llama 3)", provider="ollama", model_id="llama3:latest", context_limit=8192, api_key="", is_free=True)
        LLMConfigModel.create(display_name="Google Gemini 2.5 Flash", provider="gemini", model_id="gemini-2.5-flash", context_limit=1000000, api_key="AIzaSy123456789", is_free=True)


def capture_modal(modal: SettingsModal, output_path: str):
    modal.adjustSize()
    QApplication.processEvents()
    pixmap = modal.grab()
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    pixmap.save(output_path, "PNG")
    print(f"✅ Saved screenshot to {output_path}")


def main():
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)

    seed_settings_data()
    engine = get_style_engine()

    # 1. Dark theme (IDE)
    engine.apply_theme("ide")
    modal = SettingsModal(ai_manager=None)
    modal.resize(960, 640)
    modal.show()
    QApplication.processEvents()

    # Capture Tab 0: Général
    modal.stacked_widget.setCurrentIndex(0)
    modal.nav_btn_group.button(0).setChecked(True)
    QApplication.processEvents()
    capture_modal(modal, "temp/screens/settings_tab0_general.png")

    # Capture Tab 1: Moteurs IA
    modal.stacked_widget.setCurrentIndex(1)
    modal.nav_btn_group.button(1).setChecked(True)
    modal.ai_tab.refresh_data()
    # Simuler badges de statut pour aperçu visuel riche
    modal.ai_tab._test_cloud_key("openai", "OpenAI")
    modal.ai_tab._test_cloud_key("gemini", "Gemini")
    QApplication.processEvents()
    capture_modal(modal, "temp/screens/settings_tab1_ai_engines.png")

    # Capture Tab 2: Anki & Formats
    modal.stacked_widget.setCurrentIndex(2)
    modal.nav_btn_group.button(2).setChecked(True)
    QApplication.processEvents()
    capture_modal(modal, "temp/screens/settings_tab2_anki_sync.png")

    # Capture Tab 3: Stockage & Maintenance
    modal.stacked_widget.setCurrentIndex(3)
    modal.nav_btn_group.button(3).setChecked(True)
    modal.maint_tab.refresh_metrics()
    QApplication.processEvents()
    capture_modal(modal, "temp/screens/settings_tab3_storage_maintenance.png")

    # Capture Tab 4: Extensions
    modal.stacked_widget.setCurrentIndex(4)
    modal.nav_btn_group.button(4).setChecked(True)
    QApplication.processEvents()
    capture_modal(modal, "temp/screens/settings_tab4_addons.png")

    # 2. Light theme (JetBrains Light)
    engine.apply_theme("jetbrains_light")
    modal.refresh_theme(engine.get_theme("jetbrains_light"))
    QApplication.processEvents()

    # Light Tab 0: Général
    modal.stacked_widget.setCurrentIndex(0)
    modal.nav_btn_group.button(0).setChecked(True)
    QApplication.processEvents()
    capture_modal(modal, "temp/screens/settings_light_general.png")

    # Light Tab 1: Moteurs IA
    modal.stacked_widget.setCurrentIndex(1)
    modal.nav_btn_group.button(1).setChecked(True)
    QApplication.processEvents()
    capture_modal(modal, "temp/screens/settings_light_ai_engines.png")

    # Light Tab 2: Anki & Formats
    modal.stacked_widget.setCurrentIndex(2)
    modal.nav_btn_group.button(2).setChecked(True)
    QApplication.processEvents()
    capture_modal(modal, "temp/screens/settings_light_anki_sync.png")

    # Light Tab 3: Stockage & Maintenance
    modal.stacked_widget.setCurrentIndex(3)
    modal.nav_btn_group.button(3).setChecked(True)
    modal.maint_tab.refresh_metrics()
    QApplication.processEvents()
    capture_modal(modal, "temp/screens/settings_light_storage_maintenance.png")

    modal.close()


if __name__ == "__main__":
    main()

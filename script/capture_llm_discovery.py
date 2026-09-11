"""Script de capture d'écran pour les fonctionnalités de découverte et sélection des LLM."""

import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["ANKIFORGE_ENV"] = "testing"

from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import QApplication

from ankiforge.database.models import LLMConfigModel
from ankiforge.database.seeds.initial_seed import seed_initial_data
from ankiforge.services.profile_manager import ProfileManager
from ankiforge.ui.components.model_selector.dialog import ModelCardWidget, ModelDiscoveryDialog
from ankiforge.ui.style_engine import get_style_engine
from ankiforge.ui.views.agents_view.view import AgentsView
from ankiforge.ui.widgets.settings_modal.tabs.ai_engines_tab import AIEnginesTab

ARTIFACT_DIR = Path("/Users/tristanrigaud-humbert/.gemini/antigravity-cli/brain/fa9cb504-f162-4b31-85ba-886709b4bb68")


def main() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))

    # Initialiser le profil et la BDD SQLite
    pm = ProfileManager()
    pm.switch_profile("default")
    seed_initial_data()

    # Appliquer le thème sombre JetBrains par défaut
    style_engine = get_style_engine()
    style_engine.apply_theme("jetbrains", "ide")

    # 1. Capture de la modale de découverte et comparateur
    dlg = ModelDiscoveryDialog(current_model_id="gemini-3.5-flash-lite", picker_mode=False)
    dlg.resize(1000, 750)
    dlg.show()

    # Cocher deux cartes pour activer le tiroir de comparaison
    cards = dlg.cards_container.findChildren(ModelCardWidget)
    if len(cards) >= 2:
        cards[0].cb_compare.setChecked(True)
        cards[1].cb_compare.setChecked(True)

    app.processEvents()

    pix_dlg = QPixmap(dlg.size())
    dlg.render(pix_dlg)
    out_dlg = ARTIFACT_DIR / "llm_discovery_dialog.png"
    pix_dlg.save(str(out_dlg))
    dlg.close()
    dlg.deleteLater()
    app.processEvents()

    # 2. Capture de l'onglet Paramètres Moteurs IA
    tab = AIEnginesTab()
    tab.resize(960, 600)
    tab.show()
    tab.refresh_data()
    app.processEvents()

    pix_tab = QPixmap(tab.size())
    tab.render(pix_tab)
    out_tab = ARTIFACT_DIR / "settings_ai_engines_tab.png"
    pix_tab.save(str(out_tab))
    tab.close()
    tab.deleteLater()
    app.processEvents()

    # 2bis. Capture de la modale Settings complète avec l'onglet Moteurs IA
    from ankiforge.ui.widgets.settings_modal import SettingsModal

    settings_modal = SettingsModal()
    settings_modal.stacked_widget.setCurrentIndex(1)  # Moteurs IA
    settings_modal.nav_btns[1].setChecked(True)
    settings_modal.show()
    settings_modal.ai_tab.refresh_data()
    app.processEvents()

    pix_modal = QPixmap(settings_modal.size())
    settings_modal.render(pix_modal)
    out_modal = ARTIFACT_DIR / "settings_modal_ai_tab.png"
    pix_modal.save(str(out_modal))
    settings_modal.close()
    settings_modal.deleteLater()
    app.processEvents()

    # 3. Capture de la vue Agents avec le ModelSelectorWidget enrichi et badges affichés
    agents_view = AgentsView()
    agents_view.resize(1100, 700)
    agents_view.show()
    agents_view.refresh_data()
    # Sélectionner un modèle avec capacités pour afficher les badges
    m = LLMConfigModel.select().where(LLMConfigModel.provider == "gemini").first()
    if m:
        agents_view.engine_combo.set_current_model_id(m.id)
    app.processEvents()

    pix_agents = QPixmap(agents_view.size())
    agents_view.render(pix_agents)
    out_agents = ARTIFACT_DIR / "agents_view_model_selector.png"
    pix_agents.save(str(out_agents))
    agents_view.close()


if __name__ == "__main__":
    main()

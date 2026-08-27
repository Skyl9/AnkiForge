import os
import sys

from PySide6.QtCore import QCoreApplication, QTranslator, QSettings
from dotenv import load_dotenv

from ankiforge.database.backup import backup_database
from ankiforge.database.migration import run_migrations
from ankiforge.database.models import init_db, seed_initial_data
from ankiforge.services.ai.flexible_service import AIManager
from ankiforge.ui.main_window import MainWindow
from ankiforge.ui.theme import setup_dynamic_theme
from ankiforge.utils.logger import setup_logging
from ankiforge.utils.paths import get_project_root

os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-logging --log-level=3 --disable-skia-graphite"
os.environ["QT_LOGGING_RULES"] = "qt.webenginecontext.*=false"
# ruff : noqa: E402
from PySide6.QtWidgets import QApplication
from ankiforge.ui.widgets.profile_selector import ProfileSelectorDialog
from ankiforge.services.profile_manager import ProfileManager


def main():
    setup_logging()
    QCoreApplication.setOrganizationName("AnkiForgeOrg")
    QCoreApplication.setApplicationName("ankiforge_obsidian")

    app = QApplication(sys.argv)

    pm = ProfileManager()
    profiles = pm.list_profiles()

    selected_profile = "default"
    if not profiles:
        pm.create_profile("default")
        selected_profile = "default"
    elif len(profiles) == 1:
        selected_profile = profiles[0]
    else:
        dialog = ProfileSelectorDialog(profiles)
        if dialog.exec() == ProfileSelectorDialog.DialogCode.Accepted:
            selected_profile = dialog.get_selected_profile()
        else:
            sys.exit(0)  # Annulé

    pm.switch_profile(selected_profile)

    load_dotenv()
    init_db()
    backup_database(keep_last=5)
    run_migrations()
    seed_initial_data()
    ai_manager = AIManager()

    settings = QSettings("AnkiForgeOrg", "ankiforge_obsidian")
    lang = settings.value("ui/language", "English")
    if lang == "Français":
        translator = QTranslator()
        qm_file = get_project_root() / "src" / "ankiforge" / "ressources" / "translations" / "fr_FR.qm"

        if translator.load(str(qm_file)):
            app.installTranslator(translator)

    setup_dynamic_theme(app)

    # Initialisation et chargement sécurisé des extensions
    from ankiforge.services.plugins import get_plugin_manager

    plugin_mgr = get_plugin_manager()
    plugin_mgr.load_all_addons()

    window = MainWindow(ai_manager, selected_profile)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

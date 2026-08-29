import os
import sys

from PySide6.QtCore import QCoreApplication, QSettings, QTranslator
from dotenv import load_dotenv

from ankiforge.database.backup import backup_database
from ankiforge.database.migration import run_migrations
from ankiforge.database.models import init_db, seed_initial_data
from ankiforge.services.ai.flexible_service import AIManager
from ankiforge.ui.main_window import MainWindow
from ankiforge.ui.theme import setup_dynamic_theme
from ankiforge.utils.logger import install_crash_handlers, setup_logging, shutdown_logging
from ankiforge.utils.paths import get_resource_path

os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-logging --log-level=3 --disable-skia-graphite"
os.environ["QT_LOGGING_RULES"] = "qt.webenginecontext.*=false"
# ruff : noqa: E402
from PySide6.QtWidgets import QApplication
from ankiforge.services.profile_manager import ProfileManager
from ankiforge.ui.widgets.profile_selector import ProfileSelectorDialog


def main() -> None:
    # 1. Initialisation du logging asynchrone et des gestionnaires de crash
    setup_logging()
    install_crash_handlers()

    QCoreApplication.setOrganizationName("AnkiForgeOrg")
    QCoreApplication.setApplicationName("AnkiForge")

    app = QApplication(sys.argv)
    app.aboutToQuit.connect(shutdown_logging)

    pm = ProfileManager()
    profiles = pm.list_profiles()

    settings = QSettings("AnkiForgeOrg", "AnkiForge")
    auto_open = settings.value("profiles/auto_open_startup", False, type=bool)
    default_profile = str(settings.value("profiles/default_startup_profile", "default"))

    selected_profile = "default"
    if not profiles:
        pm.create_profile("default")
        selected_profile = "default"
    elif len(profiles) == 1:
        selected_profile = profiles[0]
    elif auto_open and default_profile in profiles:
        selected_profile = default_profile
    else:
        dialog = ProfileSelectorDialog(
            profiles,
            current_profile=default_profile if default_profile in profiles else profiles[0],
        )
        if dialog.exec() == ProfileSelectorDialog.DialogCode.Accepted:
            selected_profile = dialog.get_selected_profile()
        else:
            shutdown_logging()
            sys.exit(0)  # Annulé

    pm.switch_profile(selected_profile)

    load_dotenv()
    init_db()
    backup_database(keep_last=5)
    run_migrations()
    seed_initial_data()
    ai_manager = AIManager()

    settings = QSettings("AnkiForgeOrg", "AnkiForge")
    lang = settings.value("ui/language", "English")
    if lang == "Français":
        translator = QTranslator()
        qm_file = get_resource_path("src", "ressources", "translations", "fr_FR.qm")
        if not qm_file.exists():
            qm_file = get_resource_path("ressources", "translations", "fr_FR.qm")

        if qm_file.exists() and translator.load(str(qm_file)):
            app.installTranslator(translator)

    setup_dynamic_theme(app)

    # Initialisation et chargement sécurisé des extensions
    from ankiforge.services.plugins import get_plugin_manager

    plugin_mgr = get_plugin_manager()
    plugin_mgr.load_all_addons()

    window = MainWindow(ai_manager, selected_profile)
    window.show()

    exit_code = app.exec()
    shutdown_logging()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

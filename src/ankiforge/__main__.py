import os
import sys
from pathlib import Path

# Empêcher l'écriture de fichiers .pyc à l'exécution pour ne pas invalider la signature de code Apple
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
sys.dont_write_bytecode = True

# Support pour les bundles macOS .app (Contents/Resources sur sys.path pour les dépendances tierces et métadonnées dist-info)
if sys.platform == "darwin":
    _exe_res = Path(sys.executable).parent.parent / "Resources"
    if _exe_res.exists() and str(_exe_res) not in sys.path:
        sys.path.insert(0, str(_exe_res))
    _exe_lib = _exe_res / "lib"
    if _exe_lib.exists() and str(_exe_lib) not in sys.path:
        sys.path.insert(0, str(_exe_lib))
    try:
        _mod_res = Path(__file__).resolve().parent.parent.parent / "Resources"
        if _mod_res.exists() and str(_mod_res) not in sys.path:
            sys.path.insert(0, str(_mod_res))
    except (OSError, ValueError):
        pass

from dotenv import load_dotenv
from PySide6.QtCore import QCoreApplication, QTranslator

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
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from ankiforge.services.profile_manager import ProfileManager
from ankiforge.ui.widgets.profile_selector import ProfileSelectorDialog


def main() -> None:
    if "--help" in sys.argv or "-h" in sys.argv:
        from ankiforge import __version__

        sys.stdout.write(
            f"AnkiForge v{__version__}\n\n"
            "Options:\n"
            "  -h, --help               Affiche ce message d'aide et quitte.\n"
            "  -v, --version            Affiche la version de l'application et quitte.\n"
            "  --dev                    Force l'environnement de DÉVELOPPEMENT (~/.ankiforge-dev).\n"
            "  --prod                   Force l'environnement de PRODUCTION (~/.ankiforge).\n"
            "  --smoke-test             Exécute une vérification rapide d'intégrité binaire et quitte.\n"
            "  --clone-prod-to-dev      Clone les profils et médias de production vers le dossier dev.\n"
        )
        sys.exit(0)

    if "--version" in sys.argv or "-v" in sys.argv:
        from ankiforge import __version__

        sys.stdout.write(f"AnkiForge v{__version__}\n")
        sys.exit(0)

    if "--smoke-test" in sys.argv:
        from ankiforge import __version__

        sys.stdout.write(f"AnkiForge v{__version__} - Smoke Test Passed\n")
        sys.exit(0)

    from ankiforge.utils.environment import (
        AppEnvironment,
        clone_production_data_to_development,
        get_app_qsettings,
        get_current_environment,
        get_settings_app_name,
        get_settings_org_name,
        is_development,
        set_environment,
    )
    from ankiforge.utils.paths import get_app_data_dir, get_project_root

    # Gestion précoce des drapeaux d'environnement CLI
    if "--dev" in sys.argv:
        set_environment(AppEnvironment.DEVELOPMENT)
    elif "--prod" in sys.argv:
        set_environment(AppEnvironment.PRODUCTION)

    if "--clone-prod-to-dev" in sys.argv:
        sys.stdout.write("Clonage des données de production (~/.ankiforge) vers le développement (~/.ankiforge-dev)...\n")
        cloned, media = clone_production_data_to_development(copy_media=True)
        sys.stdout.write(f"Succès : {cloned} profil(s) et {media} média(s) copiés dans ~/.ankiforge-dev/profiles/.\n")
        sys.exit(0)

    # Chargement dynamique des variables d'environnement (.env)
    if is_development():
        root_dir = get_project_root()
        for env_file in (".env.development", ".env.dev", ".env"):
            candidate = root_dir / env_file
            if candidate.exists():
                load_dotenv(dotenv_path=candidate)
    else:
        prod_env = get_app_data_dir() / ".env"
        if prod_env.exists():
            load_dotenv(dotenv_path=prod_env)
        else:
            load_dotenv()

    # 1. Initialisation du logging asynchrone et des gestionnaires de crash
    setup_logging()
    install_crash_handlers()

    env_name = get_current_environment().value
    import logging

    logger = logging.getLogger(__name__)
    logger.info("Démarrage d'AnkiForge en environnement : [%s] (Données : %s)", env_name, get_app_data_dir())

    QCoreApplication.setOrganizationName(get_settings_org_name())
    QCoreApplication.setApplicationName(get_settings_app_name())

    app = QApplication(sys.argv)
    app.aboutToQuit.connect(shutdown_logging)

    # Application Window & Dock Icon
    icon_path = get_resource_path("src", "ressources", "icons", "ankiforge.png")
    if not icon_path.exists():
        icon_path = get_resource_path("src", "ressources", "icons", "logo.svg")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    pm = ProfileManager()
    profiles = pm.list_profiles()

    settings = get_app_qsettings()
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

    init_db()
    backup_database(keep_last=5)
    run_migrations()
    seed_initial_data()
    ai_manager = AIManager()

    settings = get_app_qsettings()
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

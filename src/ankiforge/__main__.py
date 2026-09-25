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

from ankiforge.utils.ssl_certificates import setup_ssl_certificates

# Initialisation précoce des certificats racines SSL (évite FileNotFoundError sous Nuitka/macOS)
setup_ssl_certificates()

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
import argparse

from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication

from ankiforge.services.profile_manager import ProfileManager
from ankiforge.ui.widgets.profile_selector import ProfileSelectorDialog


def parse_cli_args(argv: list[str] | None = None) -> tuple[argparse.Namespace, list[str]]:
    """
    Analyse les drapeaux en ligne de commande passés à AnkiForge.
    Supporte les options standard, de test, et d'exécution du serveur MCP headless.
    """
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("-h", "--help", action="store_true")
    parser.add_argument("-v", "--version", action="store_true")
    parser.add_argument("--smoke-test", action="store_true")
    parser.add_argument("--dev", action="store_true")
    parser.add_argument("--prod", action="store_true")
    parser.add_argument("--clone-prod-to-dev", action="store_true")
    parser.add_argument("--mcp-server", action="store_true")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--profile", type=str, default=None)

    raw_args = argv if argv is not None else sys.argv[1:]
    return parser.parse_known_args(raw_args)


def main(argv: list[str] | None = None) -> None:
    known_args, _ = parse_cli_args(argv)

    if known_args.help:
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
            "  --mcp-server             Lance le serveur MCP en mode console headless (sans interface graphique).\n"
            "  --port <port>            Port TCP d'écoute du serveur MCP (défaut : 8765).\n"
            "  --profile <nom>          Profil utilisateur et base SQLite cibles (défaut : profil actif ou 'default').\n"
        )
        sys.exit(0)

    if known_args.version:
        from ankiforge import __version__

        sys.stdout.write(f"AnkiForge v{__version__}\n")
        sys.exit(0)

    if known_args.smoke_test:
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
    if known_args.dev:
        set_environment(AppEnvironment.DEVELOPMENT)
    elif known_args.prod:
        set_environment(AppEnvironment.PRODUCTION)

    if known_args.clone_prod_to_dev:
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

    # Mode Headless : Serveur MCP autonome sans UI
    if known_args.mcp_server:
        if known_args.port < 1 or known_args.port > 65535:
            sys.stderr.write(f"Erreur : Le port {known_args.port} doit être compris entre 1 et 65535.\n")
            sys.stderr.flush()
            shutdown_logging()
            sys.exit(2)

        from ankiforge.services.ai.mcp_cli import run_mcp_server_cli

        exit_code = run_mcp_server_cli(
            port=known_args.port,
            profile_name=known_args.profile,
        )
        shutdown_logging()
        sys.exit(exit_code)

    QCoreApplication.setOrganizationName(get_settings_org_name())
    QCoreApplication.setApplicationName(get_settings_app_name())

    app = QApplication(sys.argv)
    from ankiforge.ui.theme import DesignTokens

    app.setFont(QFont(DesignTokens.FONT_MAIN, DesignTokens.FONT_SIZE_BASE))
    app.aboutToQuit.connect(shutdown_logging)

    # Application Window & Dock Icon
    icon_path = get_resource_path("src", "ressources", "icons", "ankiforge.png")
    if not icon_path.exists():
        icon_path = get_resource_path("src", "ressources", "icons", "logo.svg")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    # ── Application du thème global AVANT toute fenêtre ou dialog ──────────────
    # Garantit que le ProfileSelectorDialog au démarrage reçoit le même style
    # Fusion + QPalette + QSS que lorsqu'il est ouvert depuis MainWindow.
    setup_dynamic_theme(app)

    pm = ProfileManager()
    profiles = pm.list_profiles()

    settings = get_app_qsettings()
    auto_open = settings.value("profiles/auto_open_startup", False, type=bool)
    default_profile = str(settings.value("profiles/default_startup_profile", "default"))

    selected_profile = "default"
    if known_args.profile:
        selected_profile = known_args.profile
    elif not profiles:
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

    # Re-indexation migratoire en arrière-plan des documents indexés avec une ancienne
    # stratégie de structuration (nécessite chunk_strategy_version == 0 ou absent).
    from ankiforge.services.reindex_service import get_stale_documents

    stale_docs = get_stale_documents()
    if stale_docs:
        from ankiforge.services.workers.migration_reindex_worker import MigrationReindexWorker

        reindex_worker = MigrationReindexWorker(stale_docs, parent=window)

        def _on_reindex_finished(processed: int, errors: int) -> None:
            logger.info(
                "Re-indexation migratoire terminée : %d document(s) traité(s), %d erreur(s).",
                processed,
                errors,
            )

        reindex_worker.finished_processing.connect(_on_reindex_finished)
        logger.info("Démarrage de la re-indexation migratoire de %d document(s)...", len(stale_docs))
        reindex_worker.start()

    exit_code = app.exec()
    shutdown_logging()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

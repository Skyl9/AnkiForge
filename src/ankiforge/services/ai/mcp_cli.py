"""
Point d'entrée et runner CLI pour le serveur MCP d'AnkiForge en mode headless.
"""

from __future__ import annotations

import logging
import os
import signal
import sys
import threading
from pathlib import Path
from typing import Any

from ankiforge.database.backup import backup_database
from ankiforge.database.migration import run_migrations
from ankiforge.database.models import db, init_db, seed_initial_data
from ankiforge.services.ai.mcp_daemon import MCPServerDaemon
from ankiforge.services.profile_manager import ProfileManager
from ankiforge.utils.paths import get_active_profile, get_app_data_dir

logger = logging.getLogger(__name__)


def resolve_target_profile(profile_name: str | None = None) -> str:
    """
    Résout le profil utilisateur cible pour l'exécution du serveur MCP.

    Ordre de priorité :
    1. Nom passé explicitement (ex. via CLI `--profile`)
    2. Profil de démarrage configuré dans QSettings (si existant)
    3. Profil actuellement actif (si présent dans la liste des profils)
    4. Premier profil existant sur le disque
    5. Profil par défaut "default"
    """
    pm = ProfileManager()
    profiles = pm.list_profiles()

    if profile_name:
        return profile_name

    if profiles:
        try:
            from ankiforge.utils.environment import get_app_qsettings

            settings = get_app_qsettings()
            default_p = str(settings.value("profiles/default_startup_profile", ""))
            if default_p and default_p in profiles:
                return default_p
        except Exception:
            pass

        active = get_active_profile()
        if active and active in profiles:
            return active

        if "default" in profiles:
            return "default"

        return profiles[0]

    return "default"


def run_mcp_server_cli(
    port: int = 8765,
    profile_name: str | None = None,
    stop_event: threading.Event | None = None,
    daemon_class: type[MCPServerDaemon] = MCPServerDaemon,
    data_dir: Path | None = None,
) -> int:
    """
    Démarre et maintient le serveur MCP en mode console headless bloquant au premier plan.

    Intercepte les signaux SIGINT (Ctrl+C) et SIGTERM pour déclencher un arrêt
    propre du daemon, la fermeture des sessions clientes et la déconnexion BDD.

    Args:
        port: Port TCP d'écoute souhaité (défaut : 8765, avec repli automatique si occupé).
        profile_name: Nom du profil cible (défaut : profil actif ou 'default').
        stop_event: Événement threading optionnel permettant de déclencher l'arrêt.
        daemon_class: Classe de daemon à instancier (permet l'injection pour les tests).
        data_dir: Répertoire de données optionnel (défaut : get_app_data_dir()).

    Returns:
        int: Code de sortie (0 en cas d'arrêt propre, code d'erreur > 0 sinon).
    """
    target_profile = resolve_target_profile(profile_name)
    pm = ProfileManager()

    logger.info("Initialisation de la base SQLite pour le profil '%s'...", target_profile)
    try:
        pm.switch_profile(target_profile)
        init_db()
        backup_database(keep_last=5)
        run_migrations()
        seed_initial_data()
    except Exception as e:
        logger.error("Échec d'initialisation de la base de données pour le profil '%s': %s", target_profile, e)
        sys.stderr.write(f"Erreur : Impossible d'initialiser la base de données pour le profil '{target_profile}' : {e}\n")
        sys.stderr.flush()
        return 1

    target_data_dir = data_dir if data_dir is not None else get_app_data_dir()

    daemon = daemon_class(
        host="127.0.0.1",
        base_port=port,
        data_dir=target_data_dir,
    )

    logger.info("Démarrage du daemon MCP AnkiForge sur le port %d...", port)
    if not daemon.start(timeout=10.0):
        logger.error("Impossible de démarrer le serveur MCP sur le port %d.", port)
        sys.stderr.write(f"Erreur : Impossible de démarrer le serveur MCP sur le port {port}.\n")
        sys.stderr.flush()
        if not db.is_closed():
            db.close()
        return 1

    from ankiforge.services.ai.mcp_server import mcp

    tool_count = 0
    try:
        if hasattr(mcp, "_tool_manager") and mcp._tool_manager is not None:
            tool_count = len(mcp._tool_manager.list_tools())
    except Exception as e:
        logger.debug("Impossible de compter les outils MCP : %s", e)

    db_path = pm.get_db_path(target_profile)
    pid = os.getpid()

    banner = (
        "\n"
        "======================================================================\n"
        "  🚀 AnkiForge MCP Server — Mode Console Headless\n"
        "======================================================================\n"
        f"  Statut              : En cours d'exécution (PID: {pid})\n"
        f"  Profil actif        : {target_profile}\n"
        f"  Base de données     : {db_path}\n"
        f"  Point d'entrée SSE  : {daemon.sse_url}\n"
        f"  Port d'écoute       : {daemon.port}\n"
        f"  Jeton Bearer        : {daemon.token_file}\n"
        f"  Fichier découverte  : {daemon.state_file}\n"
        f"  Outils MCP exposés  : {tool_count} outils enregistrés\n"
        "======================================================================\n"
        "  Serveur opérationnel. Appuyez sur Ctrl+C ou envoyez SIGTERM pour arrêter.\n\n"
    )
    sys.stdout.write(banner)
    sys.stdout.flush()

    logger.info("Serveur MCP AnkiForge opérationnel sur %s (port %d)", daemon.sse_url, daemon.port)
    logger.info("Jeton d'authentification Bearer : %s", daemon.token_file)
    logger.info("Fichier d'état et découverte : %s", daemon.state_file)

    if stop_event is None:
        stop_event = threading.Event()

    def _handle_signal(signum: int, frame: Any) -> None:
        signame = "SIGINT" if signum == signal.SIGINT else "SIGTERM" if signum == signal.SIGTERM else str(signum)
        logger.info("Signal d'arrêt reçu (%s). Arrêt du serveur MCP...", signame)
        sys.stdout.write(f"\nSignal d'arrêt reçu ({signame}). Fermeture du serveur MCP AnkiForge...\n")
        sys.stdout.flush()
        stop_event.set()

    old_sigint = None
    old_sigterm = None
    try:
        old_sigint = signal.signal(signal.SIGINT, _handle_signal)
        old_sigterm = signal.signal(signal.SIGTERM, _handle_signal)
    except (ValueError, AttributeError) as e:
        logger.debug("Enregistrement des signaux ignoré (contexte threadé ou non-main) : %s", e)

    exit_code = 0
    try:
        while not stop_event.is_set():
            if not daemon.is_running:
                logger.error("Le serveur MCP s'est arrêté de manière inattendue.")
                sys.stderr.write("Erreur : Le serveur MCP s'est arrêté de manière inattendue.\n")
                sys.stderr.flush()
                exit_code = 1
                break
            stop_event.wait(0.2)
    except KeyboardInterrupt:
        logger.info("Interruption clavier (Ctrl+C) détectée.")
        sys.stdout.write("\nInterruption clavier détectée. Arrêt du serveur...\n")
        sys.stdout.flush()
    finally:
        logger.info("Arrêt du serveur MCP AnkiForge en cours...")
        daemon.stop(timeout=5.0)
        if not db.is_closed():
            db.close()

        try:
            if old_sigint is not None:
                signal.signal(signal.SIGINT, old_sigint)
            if old_sigterm is not None:
                signal.signal(signal.SIGTERM, old_sigterm)
        except (ValueError, AttributeError):
            pass

        sys.stdout.write("Serveur MCP AnkiForge arrêté avec succès.\n")
        sys.stdout.flush()

    return exit_code

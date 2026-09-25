"""
Service Daemon persistant pour le serveur MCP d'AnkiForge.

Héberge un point de terminaison HTTP/SSE sur localhost (127.0.0.1) dans un thread
de travail d'arrière-plan, sécurisé par authentification Bearer.
"""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
import os
import secrets
import socket
import stat
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from starlette.responses import PlainTextResponse

if TYPE_CHECKING:
    import uvicorn
    from mcp.server.mcpserver import MCPServer
    from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)


def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    """Vérifie si un port réseau TCP local est déjà occupé ou inaccessible."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((host, port))
            return False
        except OSError:
            return True


def find_available_port(start_port: int = 8765, max_attempts: int = 100, host: str = "127.0.0.1") -> int:
    """
    Sonde séquentiellement les ports à partir de start_port jusqu'à trouver un port libre.
    Lève un RuntimeError si aucun port n'est libre après max_attempts tentatives.
    """
    for port in range(start_port, start_port + max_attempts):
        if not is_port_in_use(port, host=host):
            return port
    raise RuntimeError(f"Impossible de trouver un port libre pour le serveur MCP après {max_attempts} tentatives (plage {start_port}-{start_port + max_attempts - 1}).")


def generate_auth_token() -> str:
    """Génère un jeton d'authentification Bearer aléatoire à haute entropie (256 bits)."""
    return secrets.token_urlsafe(32)


def save_auth_token(token: str, path: Path) -> None:
    """
    Sauvegarde le jeton Bearer sur le disque avec des permissions restreintes 0600 (lecture/écriture propriétaire).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, stat.S_IRUSR | stat.S_IWUSR)
    with open(fd, "w", encoding="utf-8") as f:
        f.write(token)
    if os.name == "posix":
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)


def write_daemon_state(
    state_file: Path,
    status: str,
    host: str,
    port: int,
    token: str,
    token_file: Path,
    pid: int | None = None,
) -> None:
    """Publie l'état d'exécution et les métadonnées de connexion du serveur MCP en JSON sécurisé (0600)."""
    state_file.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "status": status,
        "host": host,
        "port": port,
        "url": f"http://{host}:{port}/sse",
        "token": token,
        "token_path": str(token_file.resolve()),
        "pid": pid if pid is not None else os.getpid(),
        "started_at": datetime.now(UTC).isoformat(),
    }
    content = json.dumps(payload, indent=2, ensure_ascii=False)
    fd = os.open(str(state_file), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, stat.S_IRUSR | stat.S_IWUSR)
    with open(fd, "w", encoding="utf-8") as f:
        f.write(content)
    if os.name == "posix":
        os.chmod(state_file, stat.S_IRUSR | stat.S_IWUSR)


def read_daemon_state(state_file: Path) -> dict[str, Any] | None:
    """Lit et désérialise le fichier d'état du serveur MCP s'il existe."""
    if not state_file.is_file():
        return None
    try:
        data = json.loads(state_file.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
        return None
    except Exception as e:
        logger.warning("Échec de lecture du fichier d'état MCP %s: %s", state_file, e)
        return None


def cleanup_daemon_state(token_file: Path, state_file: Path, mark_stopped: bool = True) -> None:
    """
    Supprime le jeton de session et marque ou supprime le fichier d'état lors de l'arrêt du daemon.
    """
    try:
        token_file.unlink(missing_ok=True)
    except Exception as e:
        logger.warning("Impossible de supprimer le fichier de token MCP %s: %s", token_file, e)

    try:
        if mark_stopped and state_file.is_file():
            data = read_daemon_state(state_file) or {}
            data["status"] = "stopped"
            data["stopped_at"] = datetime.now(UTC).isoformat()
            content = json.dumps(data, indent=2, ensure_ascii=False)
            fd = os.open(str(state_file), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, stat.S_IRUSR | stat.S_IWUSR)
            with open(fd, "w", encoding="utf-8") as f:
                f.write(content)
            if os.name == "posix":
                os.chmod(state_file, stat.S_IRUSR | stat.S_IWUSR)
        elif not mark_stopped:
            state_file.unlink(missing_ok=True)
    except Exception as e:
        logger.warning("Impossible de mettre à jour le fichier d'état MCP %s: %s", state_file, e)


class BearerAuthMiddleware:
    """
    Middleware ASGI d'authentification Bearer pour sécuriser les endpoints HTTP/SSE du daemon MCP.
    Rejette toute requête non authentifiée ou avec un jeton invalide avec un code 401 Unauthorized.
    """

    def __init__(self, app: ASGIApp, token: str) -> None:
        self.app = app
        self.token = token

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            headers = dict(scope.get("headers", []))
            raw_auth = headers.get(b"authorization", b"")

            try:
                auth_header = raw_auth.decode("utf-8").strip()
            except UnicodeDecodeError:
                logger.warning("En-tête Authorization non-UTF8 reçu sur le serveur MCP.")
                response = PlainTextResponse(
                    "Unauthorized: Invalid Authorization header encoding",
                    status_code=401,
                    headers={"WWW-Authenticate": 'Bearer realm="ankiforge-mcp"'},
                )
                await response(scope, receive, send)
                return

            expected_header = f"Bearer {self.token}"
            if not auth_header or not hmac.compare_digest(auth_header, expected_header):
                logger.warning("Tentative d'accès non autorisée au serveur MCP (jeton Bearer manquant ou invalide).")
                response = PlainTextResponse(
                    "Unauthorized: Missing or invalid Bearer token",
                    status_code=401,
                    headers={"WWW-Authenticate": 'Bearer realm="ankiforge-mcp"'},
                )
                await response(scope, receive, send)
                return

        await self.app(scope, receive, send)


class MCPServerDaemon:
    """
    Gestionnaire de cycle de vie du serveur MCP AnkiForge en arrière-plan.

    Démarre une application Starlette / Uvicorn SSE sur 127.0.0.1 dans un thread
    de travail dédié, avec repli de port automatique, authentification Bearer
    et publication d'état sur le disque.
    """

    def __init__(
        self,
        mcp_server: MCPServer | None = None,
        host: str = "127.0.0.1",
        base_port: int = 8765,
        data_dir: Path | None = None,
        log_level: str = "warning",
    ) -> None:
        from ankiforge.utils.paths import get_app_data_dir

        self._mcp_server = mcp_server
        self._host = host
        self._base_port = base_port
        self._data_dir = data_dir if data_dir is not None else get_app_data_dir()
        self._log_level = log_level

        self._port: int | None = None
        self._token: str | None = None
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._is_running: bool = False
        self._lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        """Indique si le serveur MCP est actuellement actif et à l'écoute."""
        return self._is_running and self._thread is not None and self._thread.is_alive()

    @property
    def port(self) -> int | None:
        """Retourne le port réseau sur lequel écoute le serveur MCP actif."""
        return self._port

    @property
    def host(self) -> str:
        """Retourne l'adresse d'hôte (par défaut 127.0.0.1)."""
        return self._host

    @property
    def token(self) -> str | None:
        """Retourne le jeton Bearer généré pour la session active."""
        return self._token

    @property
    def sse_url(self) -> str | None:
        """Retourne l'URL complète du point de terminaison SSE si le serveur est actif."""
        if self._port is not None:
            return f"http://{self._host}:{self._port}/sse"
        return None

    @property
    def token_file(self) -> Path:
        """Chemin vers le fichier de persistance du jeton Bearer."""
        return self._data_dir / "mcp_auth_token"

    @property
    def state_file(self) -> Path:
        """Chemin vers le fichier de persistance de l'état d'exécution du daemon."""
        return self._data_dir / "mcp_server.json"

    def start(self, timeout: float = 5.0) -> bool:
        """
        Démarre le serveur MCP de manière asynchrone dans un thread de travail d'arrière-plan.
        Attends jusqu'à `timeout` secondes que le serveur Uvicorn soit prêt à recevoir des requêtes.

        Returns:
            bool: True si le serveur a démarré avec succès, False sinon.
        """
        with self._lock:
            if self.is_running:
                logger.info("Le daemon MCP est déjà en cours d'exécution sur le port %d.", self._port)
                return True

            # 1. Résolution de l'instance MCPServer
            mcp_instance = self._mcp_server
            if mcp_instance is None:
                from ankiforge.services.ai.mcp_server import mcp

                mcp_instance = mcp
                self._mcp_server = mcp

            # 2. Allocation dynamique d'un port disponible avec boucle de repli
            import uvicorn

            max_port_attempts = 20
            start_port = self._base_port

            for _attempt in range(max_port_attempts):
                port = find_available_port(start_port=start_port, host=self._host)

                # 3. Génération et sécurisation du jeton Bearer (0600)
                token = generate_auth_token()
                save_auth_token(token, self.token_file)

                # 4. Construction de l'application ASGI avec middleware de sécurité
                raw_sse_app = mcp_instance.sse_app(host=self._host)
                secured_app = BearerAuthMiddleware(raw_sse_app, token=token)

                # 5. Configuration Uvicorn sans signaux système intrusifs
                config = uvicorn.Config(
                    app=secured_app,
                    host=self._host,
                    port=port,
                    log_level=self._log_level,
                    loop="asyncio",
                )
                server = uvicorn.Server(config)
                self._server = server

                # 6. Démarrage de la boucle d'événements dans un thread dédié
                def _run_server(srv: uvicorn.Server) -> None:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    self._loop = loop
                    try:
                        loop.run_until_complete(srv.serve())
                    except (Exception, asyncio.CancelledError):
                        pass
                    finally:
                        try:
                            pending = [t for t in asyncio.all_tasks(loop) if not t.done()]
                            for task in pending:
                                task.cancel()
                            if pending:
                                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                        except Exception:
                            pass
                        loop.close()

                thread = threading.Thread(
                    target=_run_server,
                    args=(server,),
                    name=f"MCPServerDaemon-{port}",
                    daemon=True,
                )
                self._thread = thread
                thread.start()

                # 7. Attente synchronisée de la mise à disposition effective du serveur
                deadline = time.monotonic() + timeout
                while not getattr(server, "started", False) and time.monotonic() < deadline:
                    if not thread.is_alive():
                        # Échec immédiat (collision de bind intervenue après probe)
                        break
                    time.sleep(0.02)

                if getattr(server, "started", False):
                    self._port = port
                    self._token = token
                    self._is_running = True

                    # 8. Publication des métadonnées d'état (0600)
                    write_daemon_state(
                        state_file=self.state_file,
                        status="running",
                        host=self._host,
                        port=port,
                        token=token,
                        token_file=self.token_file,
                        pid=os.getpid(),
                    )

                    logger.info("Daemon MCP AnkiForge opérationnel sur %s (port %d).", self.sse_url, port)
                    return True

                # Collision ou échec, nettoyage et essai du port suivant
                self.stop(timeout=1.0)
                start_port = port + 1

            logger.error("Le daemon MCP n'a pas pu démarrer après %d tentatives.", max_port_attempts)
            return False

    def stop(self, timeout: float = 5.0) -> None:
        """
        Arrête proprement le daemon MCP, ferme les sessions clientes actives et met à jour l'état.
        """
        with self._lock:
            if not self._is_running and (self._thread is None or not self._thread.is_alive()):
                cleanup_daemon_state(token_file=self.token_file, state_file=self.state_file, mark_stopped=True)
                return

            logger.info("Arrêt du daemon MCP AnkiForge en cours...")

            # 1. Fermeture des sessions clientes actives (annulation des tâches SSE dans l'event loop)
            if self._loop is not None and self._loop.is_running():
                try:

                    def _cancel_active_sessions() -> None:
                        if self._loop is not None and self._loop.is_running():
                            for task in asyncio.all_tasks(self._loop):
                                task.cancel()

                    self._loop.call_soon_threadsafe(_cancel_active_sessions)
                except Exception as e:
                    logger.debug("Exception lors de l'annulation des sessions SSE : %s", e)

            # 2. Signalisation d'arrêt à Uvicorn
            if self._server is not None:
                self._server.should_exit = True

            # 3. Attente de la fin du thread de travail
            if self._thread is not None and self._thread.is_alive():
                self._thread.join(timeout=timeout)

            # 4. Nettoyage du jeton et marquage de l'état "stopped"
            cleanup_daemon_state(token_file=self.token_file, state_file=self.state_file, mark_stopped=True)

            self._is_running = False
            self._port = None
            self._token = None
            self._server = None
            self._thread = None
            self._loop = None

            logger.info("Daemon MCP arrêté avec succès.")

    def __enter__(self) -> MCPServerDaemon:
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.stop()

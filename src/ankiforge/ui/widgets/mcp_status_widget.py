"""
Bouton de navigation et supervision MCP pour la barre latérale (Sidebar) AnkiForge.

Affiche en temps réel le statut d'écoute du démon MCP (actif, inactif, erreur, mutation)
directement sous le bouton Paramètres de la barre latérale, en respectant la charte visuelle
de l'IDE (hauteur 36px, icône 20px, typographie, repli/dépliage et survol).
Fournit un menu contextuel complet (copie JSON agy/Claude, token, URL SSE,
démarrage/arrêt/redémarrage, accès direct aux préférences).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from PySide6.QtCore import QPoint, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QGuiApplication, QMouseEvent
from PySide6.QtWidgets import QMenu, QPushButton, QWidget

from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class MCPStatusWidget(QPushButton):
    """
    Bouton de supervision permanente du serveur MCP positionné dans la barre latérale.

    Hérite de QPushButton pour s'intégrer harmonieusement dans le footer de la Sidebar
    (juste en dessous du bouton Paramètres) avec support du repli 68px/260px.
    """

    start_requested = Signal()
    stop_requested = Signal()
    restart_requested = Signal()
    open_preferences_requested = Signal()

    def __init__(
        self,
        initial_status: str = "stopped",
        initial_port: int = 8765,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("SidebarMCPBtn")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(36)
        self.setIconSize(QSize(20, 20))

        # Attribut de compatibilité pour le code et les tests accédant à widget.badge
        self.badge = self

        self._status = initial_status
        self._port: int = initial_port
        self._host: str = "127.0.0.1"
        self._token: str | None = None
        self._message: str = ""
        self._pre_mutation_status: str = initial_status
        self._mutation_timer: QTimer | None = None
        self._collapsed: bool = False
        self._current_profile: Any | None = None
        self._label_text: str = ""

        self.clicked.connect(self._on_clicked)
        self.set_status(initial_status, port=initial_port)

    @property
    def current_status(self) -> str:
        """Retourne l'état courant : running, stopped, error ou mutating."""
        return self._status

    @property
    def port(self) -> int:
        """Retourne le port réseau configuré ou actif."""
        return self._port

    @property
    def host(self) -> str:
        """Retourne l'hôte configuré (127.0.0.1 par défaut)."""
        return self._host

    @property
    def token(self) -> str | None:
        """Retourne le jeton Bearer d'authentification."""
        return self._token

    @token.setter
    def token(self, value: str | None) -> None:
        self._token = value

    @property
    def sse_url(self) -> str:
        """Retourne l'URL SSE complète du point de terminaison."""
        return f"http://{self._host}:{self._port}/sse"

    def set_collapsed(self, collapsed: bool) -> None:
        """Ajuste l'affichage lors du repli / dépliage de la barre latérale."""
        self._collapsed = collapsed
        self._update_display()

    def set_status(
        self,
        status: str,
        port: int | None = None,
        host: str | None = None,
        token: str | None = None,
        message: str | None = None,
    ) -> None:
        """Met à jour l'état visuel et les métadonnées de connexion du serveur MCP."""
        self._status = status
        if port is not None:
            self._port = port
        if host is not None:
            self._host = host
        if token is not None:
            self._token = token
        if message is not None:
            self._message = message

        self._update_display()

    def _update_display(self) -> None:
        """Met à jour l'icône, le texte, l'infobulle et le style selon l'état actuel."""
        port_suffix = f" :{self._port}" if self._port else ""

        if self._status == "running":
            label = f"  Serveur MCP{port_suffix}"
            tooltip = f"Serveur MCP actif sur http://{self._host}:{self._port}/sse\nClic pour copier la configuration ou gérer le serveur"
            icon_color = getattr(self._current_profile, "color_green", DesignTokens.COLOR_GREEN) if self._current_profile else DesignTokens.COLOR_GREEN
        elif self._status == "stopped":
            label = "  Serveur MCP (Inactif)"
            tooltip = f"Serveur MCP inactif (port configuré : {self._port})\nClic pour démarrer ou configurer"
            icon_color = getattr(self._current_profile, "text_secondary", DesignTokens.TEXT_SECONDARY) if self._current_profile else DesignTokens.TEXT_SECONDARY
        elif self._status == "mutating":
            label = "  Serveur MCP (Mutation...)"
            tooltip = f"Traitement d'une mutation de données reçue via MCP sur le port {self._port}"
            icon_color = getattr(self._current_profile, "color_yellow", DesignTokens.COLOR_YELLOW) if self._current_profile else DesignTokens.COLOR_YELLOW
        elif self._status == "error":
            detail = f" ({self._message})" if self._message else ""
            label = "  Serveur MCP (Erreur)"
            tooltip = f"Erreur du serveur MCP{detail}\nClic pour afficher les actions ou redémarrer"
            icon_color = getattr(self._current_profile, "color_red", DesignTokens.COLOR_RED) if self._current_profile else DesignTokens.COLOR_RED
        else:
            label = f"  Serveur MCP ({self._status})"
            tooltip = f"État du serveur MCP : {self._status}"
            icon_color = getattr(self._current_profile, "text_secondary", DesignTokens.TEXT_SECONDARY) if self._current_profile else DesignTokens.TEXT_SECONDARY

        self._label_text = label
        self.setIcon(load_phosphor_icon("ph.plugs-connected", color=icon_color))

        if self._collapsed:
            self.setText("")
        else:
            self.setText(label)

        self.setToolTip(tooltip)
        self.setProperty("status", self._status)

        style = self.style()
        if style is not None:
            style.unpolish(self)
            style.polish(self)

    def flash_mutation(self, duration_ms: int = 1500) -> None:
        """
        Déclenche un flash visuel 'mutating' temporaire lors de modifications de cartes/styles,
        puis restaure automatiquement l'état précédent.
        """
        if self._status != "mutating":
            self._pre_mutation_status = self._status

        self.set_status("mutating")

        if self._mutation_timer is not None:
            self._mutation_timer.stop()

        self._mutation_timer = QTimer(self)
        self._mutation_timer.setSingleShot(True)
        self._mutation_timer.timeout.connect(self._revert_mutation_flash)
        self._mutation_timer.start(duration_ms)

    def _revert_mutation_flash(self) -> None:
        """Rétablit le statut antérieur au flash de mutation."""
        self.set_status(self._pre_mutation_status)

    def get_client_config(self) -> dict[str, Any]:
        """Génère le dictionnaire de configuration client Claude Desktop / Antigravity agy."""
        config: dict[str, Any] = {
            "mcpServers": {
                "ankiforge": {
                    "url": self.sse_url,
                }
            }
        }
        if self._token:
            config["mcpServers"]["ankiforge"]["headers"] = {
                "Authorization": f"Bearer {self._token}",
            }
        return config

    def get_client_config_json(self) -> str:
        """Retourne la configuration client formatée en JSON indenté."""
        return json.dumps(self.get_client_config(), indent=2, ensure_ascii=False)

    def copy_client_config(self) -> None:
        """Copie le bloc JSON de configuration client dans le presse-papiers."""
        cfg_json = self.get_client_config_json()
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(cfg_json)
            show_toast(self, "Configuration client MCP copiée dans le presse-papiers.")
            logger.info("Configuration client MCP copiée dans le presse-papiers.")

    def copy_sse_url(self) -> None:
        """Copie l'URL du point de terminaison SSE dans le presse-papiers."""
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self.sse_url)
            show_toast(self, f"URL SSE copiée : {self.sse_url}")
            logger.info("URL SSE copiée : %s", self.sse_url)

    def copy_token(self) -> None:
        """Copie le jeton d'authentification Bearer dans le presse-papiers."""
        if not self._token:
            from ankiforge.services.ai.mcp_daemon import read_daemon_state
            from ankiforge.utils.paths import get_app_data_dir

            state_file = get_app_data_dir() / "mcp_server.json"
            state = read_daemon_state(state_file)
            if state and state.get("token"):
                self._token = state["token"]

        if self._token:
            clipboard = QGuiApplication.clipboard()
            if clipboard is not None:
                clipboard.setText(self._token)
                show_toast(self, "Jeton d'authentification MCP copié.")
                logger.info("Jeton d'authentification MCP copié.")
        else:
            show_toast(self, "Aucun jeton d'authentification disponible (serveur inactif).", is_error=True)

    def show_context_menu(self, pos: QPoint | None = None) -> None:
        """Affiche le menu contextuel interactif à la position indiquée."""
        if pos is None:
            pos = self.mapToGlobal(QPoint(self.width() + 4, 0))

        menu = QMenu(self)

        # Section 1 : Actions de copie
        act_copy_config = QAction(load_phosphor_icon("ph.copy"), "Copier la configuration JSON (Claude / agy)", self)
        act_copy_config.triggered.connect(self.copy_client_config)
        menu.addAction(act_copy_config)

        act_copy_url = QAction(load_phosphor_icon("ph.link"), f"Copier l'URL SSE ({self.sse_url})", self)
        act_copy_url.triggered.connect(self.copy_sse_url)
        menu.addAction(act_copy_url)

        act_copy_token = QAction(load_phosphor_icon("ph.key"), "Copier le token d'authentification", self)
        act_copy_token.triggered.connect(self.copy_token)
        menu.addAction(act_copy_token)

        menu.addSeparator()

        # Section 2 : Pilotage du serveur
        is_running = self._status == "running"
        act_start = QAction(load_phosphor_icon("ph.play"), "Démarrer le serveur", self)
        act_start.setEnabled(not is_running)
        act_start.triggered.connect(self.start_requested.emit)
        menu.addAction(act_start)

        act_stop = QAction(load_phosphor_icon("ph.stop"), "Arrêter le serveur", self)
        act_stop.setEnabled(is_running)
        act_stop.triggered.connect(self.stop_requested.emit)
        menu.addAction(act_stop)

        act_restart = QAction(load_phosphor_icon("ph.arrows-clockwise"), "Redémarrer le serveur", self)
        act_restart.setEnabled(is_running)
        act_restart.triggered.connect(self.restart_requested.emit)
        menu.addAction(act_restart)

        menu.addSeparator()

        # Section 3 : Accès aux paramètres
        act_prefs = QAction(load_phosphor_icon("ph.gear"), "Préférences MCP...", self)
        act_prefs.triggered.connect(self.open_preferences_requested.emit)
        menu.addAction(act_prefs)

        menu.exec(pos)

    def _on_clicked(self) -> None:
        """Déclenche l'ouverture du menu contextuel au clic gauche."""
        pos = self.mapToGlobal(QPoint(self.width() + 4, 0))
        self.show_context_menu(pos)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Gère le clic droit pour ouvrir également le menu contextuel à la position du curseur."""
        if event.button() == Qt.MouseButton.RightButton:
            self.show_context_menu(event.globalPosition().toPoint())
            event.accept()
            return
        super().mousePressEvent(event)

    def refresh_theme(self, profile: Any) -> None:
        """Actualise le style sémantique et la couleur de l'icône lors d'un changement de thème."""
        self._current_profile = profile
        self._update_display()


# Alias rétrocompatible
SidebarMCPItem = MCPStatusWidget

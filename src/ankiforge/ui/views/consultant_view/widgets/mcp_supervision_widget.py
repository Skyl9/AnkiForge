"""Cockpit de supervision opérationnelle et de configuration client pour le serveur MCP local.

Permet le pilotage en direct du cycle de vie du démon (démarrer/arrêter/redémarrer/tester),
l'inspection et la copie sécurisée des endpoints HTTP/SSE et du jeton Bearer, la génération
instantanée des configurations clientes prêtes à l'emploi (Claude, agy, Cursor, cURL) et
l'ouverture directe des fichiers de configuration sur le système.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFont, QGuiApplication
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ankiforge.ui.components.badges import Badge
from ankiforge.ui.components.buttons import (
    IconButton,
    PrimaryButton,
    SecondaryButton,
    apply_compact_style,
)
from ankiforge.ui.components.tabs.segmented_tab_bar import SegmentedTabBar
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.i18n import tr
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class MCPSupervisionWidget(QWidget):
    """Cockpit opérationnel du serveur MCP en deux colonnes équilibrées sans défilement (Zero-Scroll)."""

    start_requested = Signal()
    stop_requested = Signal()
    restart_requested = Signal()
    rotate_token_requested = Signal()
    open_preferences_requested = Signal()
    ping_finished = Signal(bool, str)

    def __init__(
        self,
        initial_status: str = "stopped",
        initial_port: int = 8765,
        initial_token: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("MCPSupervisionWidget")

        self._status = initial_status
        self._port = initial_port
        self._host = "127.0.0.1"
        self._token = initial_token
        self._token_visible = False
        self._active_snippet_key = "claude"
        self.pending_request: dict[str, Any] | None = None

        self._started_at: datetime | None = datetime.now() if initial_status == "running" else None
        self._uptime_timer = QTimer(self)
        self._uptime_timer.setInterval(10000)
        self._uptime_timer.timeout.connect(self._update_uptime_display)
        self.ping_finished.connect(self._on_ping_finished)

        if self._token is None:
            self._load_token_from_disk()

        self._setup_ui()
        self.set_status(initial_status, port=initial_port, token=self._token)
        self._init_activity_tracker_listener()

    @property
    def current_status(self) -> str:
        return self._status

    @property
    def port(self) -> int:
        return self._port

    @property
    def host(self) -> str:
        return self._host

    @property
    def token(self) -> str | None:
        return self._token

    @property
    def url(self) -> str:
        return f"http://{self._host}:{self._port}/mcp"

    @property
    def sse_url(self) -> str:
        return f"http://{self._host}:{self._port}/sse"

    def _load_token_from_disk(self) -> None:
        try:
            from ankiforge.services.ai.mcp_daemon import read_daemon_state
            from ankiforge.utils.paths import get_app_data_dir

            state_file = get_app_data_dir() / "mcp_server.json"
            state = read_daemon_state(state_file)
            if state and state.get("token"):
                self._token = str(state["token"])
        except Exception as exc:
            logger.debug("Impossible de charger le jeton MCP depuis le disque : %s", exc)

    def _setup_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(*DesignTokens.DESIGN_SYSTEM_MARGES["mcp_root"])
        root_layout.setSpacing(DesignTokens.DESIGN_SYSTEM_SPACING["mcp_root"])

        # ── 1. En-tête compact dans sa carte conteneur ─────────────────────
        self.card_header = self._create_card("mcp_card_header")
        header_layout = QHBoxLayout(self.card_header)
        header_layout.setContentsMargins(16, 10, 16, 10)
        header_layout.setSpacing(12)

        icon_lbl = QLabel()
        icon_lbl.setStyleSheet("border: none; background: transparent;")
        icon_lbl.setPixmap(load_phosphor_icon("ph.plugs-connected", color=DesignTokens.ACCENT_PRIMARY).pixmap(24, 24))
        header_layout.addWidget(icon_lbl)

        title_info_col = QVBoxLayout()
        title_info_col.setSpacing(2)

        lbl_title = QLabel(self.tr("Serveur MCP Local (Model Context Protocol)"))
        lbl_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 16px; font-weight: 700; background: transparent; border: none;")
        title_info_col.addWidget(lbl_title)

        lbl_subtitle = QLabel(self.tr("Pont bidirectionnel pour vos agents IA (Claude Code, agy, Cursor) sans surcoût dans AnkiForge."))
        lbl_subtitle.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 12px; background: transparent; border: none;")
        lbl_subtitle.setWordWrap(True)
        title_info_col.addWidget(lbl_subtitle)
        header_layout.addLayout(title_info_col, 1)

        self.btn_open_prefs = SecondaryButton(self.tr("Préférences"))
        self.btn_open_prefs.setIcon(load_phosphor_icon("ph.gear", color=DesignTokens.TEXT_SECONDARY))
        self.btn_open_prefs.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_open_prefs.setToolTip(self.tr("Configurer les options globales du serveur MCP et des fournisseurs IA"))
        self.btn_open_prefs.clicked.connect(self.open_preferences_requested.emit)
        apply_compact_style(self.btn_open_prefs, height=32)
        header_layout.addWidget(self.btn_open_prefs)

        root_layout.addWidget(self.card_header)

        # ── 2. Bandeau Requête Contextuelle Externe (Rétractable) ──────────
        self.banner_context_request = QFrame()
        self.banner_context_request.setObjectName("mcp_banner_context_request")
        self.banner_context_request.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.banner_context_request.setVisible(False)
        self.banner_context_request.setStyleSheet(f"""
            QFrame#mcp_banner_context_request {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-left: 3px solid {DesignTokens.ACCENT_PRIMARY};
                border-radius: 8px;
                padding: 10px;
            }}
            QFrame#mcp_banner_context_request QLabel {{
                border: none;
                background: transparent;
            }}
        """)
        banner_layout = QVBoxLayout(self.banner_context_request)
        banner_layout.setContentsMargins(12, 10, 12, 10)
        banner_layout.setSpacing(8)

        banner_top = QHBoxLayout()
        banner_top.setSpacing(8)

        icon_request = QLabel()
        icon_request.setStyleSheet("background: transparent; border: none;")
        icon_request.setPixmap(load_phosphor_icon("ph.sparkle", color=DesignTokens.ACCENT_PRIMARY).pixmap(18, 18))
        banner_top.addWidget(icon_request)

        lbl_req_title = QLabel(self.tr("Demande d'assistance contextuelle prête pour votre agent externe"))
        lbl_req_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 13px; font-weight: 600; background: transparent; border: none;")
        banner_top.addWidget(lbl_req_title)
        banner_top.addStretch()

        self.btn_dismiss_request = IconButton("ph.x", tooltip=self.tr("Ignorer cette demande"), size=20)
        self.btn_dismiss_request.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_dismiss_request.clicked.connect(self._dismiss_pending_request)
        banner_top.addWidget(self.btn_dismiss_request)
        banner_layout.addLayout(banner_top)

        self.lbl_request_context = QLabel()
        self.lbl_request_context.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11.5px; background: transparent; border: none;")
        banner_layout.addWidget(self.lbl_request_context)

        self.edit_request_prompt = QPlainTextEdit()
        self.edit_request_prompt.setObjectName("mcp_edit_request_prompt")
        self.edit_request_prompt.setReadOnly(True)
        self.edit_request_prompt.setMaximumHeight(70)
        self.edit_request_prompt.setStyleSheet(f"""
            QPlainTextEdit#mcp_edit_request_prompt {{
                background-color: {DesignTokens.BG_INPUT};
                color: {DesignTokens.TEXT_PRIMARY};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
                font-family: {DesignTokens.FONT_CODE};
                font-size: 11.5px;
                padding: 6px;
            }}
        """)
        banner_layout.addWidget(self.edit_request_prompt)

        btn_row_req = QHBoxLayout()
        btn_row_req.addStretch()

        self.btn_copy_request_prompt = PrimaryButton(self.tr("Copier le prompt pour mon agent (CLI / Claude)"))
        self.btn_copy_request_prompt.setIcon(load_phosphor_icon("ph.copy", color=DesignTokens.TEXT_ON_ACCENT))
        self.btn_copy_request_prompt.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_copy_request_prompt.clicked.connect(self._copy_request_prompt)
        btn_row_req.addWidget(self.btn_copy_request_prompt)

        banner_layout.addLayout(btn_row_req)
        root_layout.addWidget(self.banner_context_request)

        # ── 3. Cockpit 2 Colonnes Équilibrées (50% / 50%) ──────────────────
        columns_layout = QHBoxLayout()
        columns_layout.setContentsMargins(0, 0, 0, 0)
        columns_layout.setSpacing(16)

        # ── Colonne Gauche : Pilotage opérationnel & Accès réseau ──────────
        col_left = QVBoxLayout()
        col_left.setSpacing(14)

        # 3.1 Carte Pilotage Opérationnel
        self.card_lifecycle = self._create_card("mcp_card_lifecycle")
        lifecycle_layout = QVBoxLayout(self.card_lifecycle)
        lifecycle_layout.setContentsMargins(16, 14, 16, 14)
        lifecycle_layout.setSpacing(12)

        # En-tête de section avec badge de statut
        header_ops_row = QHBoxLayout()
        header_ops_row.setSpacing(8)

        lbl_ops_sec = QLabel(self.tr("ÉTAT DU SERVEUR & PILOTAGE"))
        lbl_ops_sec.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: 700; letter-spacing: 0.5px; background: transparent; border: none;")
        header_ops_row.addWidget(lbl_ops_sec)
        header_ops_row.addStretch()

        self.status_badge = Badge(self.tr("Arrêté"), variant="neutral")
        header_ops_row.addWidget(self.status_badge)
        lifecycle_layout.addLayout(header_ops_row)

        # Ligne d'état réseau et Uptime
        status_row = QHBoxLayout()
        status_row.setSpacing(10)

        self.lbl_port_info = QLabel(tr("Port : %1", self._port))
        self.lbl_port_info.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: 600; background: transparent; border: none;")
        status_row.addWidget(self.lbl_port_info)

        self.lbl_transport_info = QLabel(self.tr("Streamable HTTP + SSE"))
        self.lbl_transport_info.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 12px; background: transparent; border: none;")
        status_row.addWidget(self.lbl_transport_info)

        self.lbl_uptime = QLabel(self.tr("Uptime : —"))
        self.lbl_uptime.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 12px; background: transparent; border: none;")
        status_row.addWidget(self.lbl_uptime)
        status_row.addStretch()

        # Bouton Tester la connexion (Ping)
        self.btn_ping = SecondaryButton(self.tr("Tester (Ping)"))
        self.btn_ping.setIcon(load_phosphor_icon("ph.broadcast", color=DesignTokens.TEXT_PRIMARY))
        self.btn_ping.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_ping.setToolTip(self.tr("Vérifier localement la réponse du serveur MCP sur le port actif"))
        apply_compact_style(self.btn_ping, height=28)
        self.btn_ping.clicked.connect(self.test_connection_ping)
        status_row.addWidget(self.btn_ping)

        self.lbl_ping_result = QLabel("")
        self.lbl_ping_result.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; background: transparent; border: none;")
        status_row.addWidget(self.lbl_ping_result)

        lifecycle_layout.addLayout(status_row)

        # Boutons d'actions opérationnelles colorés et expressifs
        btn_row_ops = QHBoxLayout()
        btn_row_ops.setSpacing(8)

        self.btn_start = PrimaryButton(self.tr("Démarrer"))
        self.btn_start.setObjectName("mcp_btn_start")
        self.btn_start.setIcon(load_phosphor_icon("ph.play", color=DesignTokens.COLOR_GREEN))
        self.btn_start.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_start.setToolTip(self.tr("Démarrer le démon MCP local pour écouter les requêtes d'agents"))
        apply_compact_style(self.btn_start, height=32)
        self.btn_start.clicked.connect(self.start_requested.emit)
        btn_row_ops.addWidget(self.btn_start)

        self.btn_stop = SecondaryButton(self.tr("Arrêter"))
        self.btn_stop.setObjectName("mcp_btn_stop")
        self.btn_stop.setIcon(load_phosphor_icon("ph.stop", color=DesignTokens.COLOR_RED))
        self.btn_stop.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_stop.setToolTip(self.tr("Arrêter le démon MCP et fermer proprement les flux SSE"))
        apply_compact_style(self.btn_stop, height=32)
        self.btn_stop.clicked.connect(self.stop_requested.emit)
        btn_row_ops.addWidget(self.btn_stop)

        self.btn_restart = SecondaryButton(self.tr("Redémarrer"))
        self.btn_restart.setObjectName("mcp_btn_restart")
        self.btn_restart.setIcon(load_phosphor_icon("ph.arrows-clockwise", color=DesignTokens.COLOR_YELLOW))
        self.btn_restart.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_restart.setToolTip(self.tr("Redémarrer le serveur pour appliquer de nouveaux paramètres ou réinitialiser les connexions"))
        apply_compact_style(self.btn_restart, height=32)
        self.btn_restart.clicked.connect(self.restart_requested.emit)
        btn_row_ops.addWidget(self.btn_restart)
        btn_row_ops.addStretch()

        self._apply_ops_button_styles()
        lifecycle_layout.addLayout(btn_row_ops)

        # Mini-KPIs de supervision opérationnelle
        kpis_row = QHBoxLayout()
        kpis_row.setSpacing(10)

        # KPI 1 : Requêtes reçues
        self.kpi_box_calls, self.lbl_kpi_calls = self._create_kpi_box(
            icon_name="ph.lightning",
            title=self.tr("Requêtes traitées"),
            initial_value="0",
        )
        kpis_row.addWidget(self.kpi_box_calls, 1)

        # KPI 2 : Dernier outil invoqué
        self.kpi_box_last_tool, self.lbl_kpi_last_tool = self._create_kpi_box(
            icon_name="ph.wrench",
            title=self.tr("Dernier outil invoqué"),
            initial_value=self.tr("Aucun appel"),
        )
        kpis_row.addWidget(self.kpi_box_last_tool, 1)

        lifecycle_layout.addLayout(kpis_row)
        col_left.addWidget(self.card_lifecycle)

        # 3.2 Carte Points de Terminaison & Jeton d'Authentification
        self.card_endpoints = self._create_card("mcp_card_endpoints")
        endpoints_layout = QVBoxLayout(self.card_endpoints)
        endpoints_layout.setContentsMargins(16, 14, 16, 14)
        endpoints_layout.setSpacing(10)

        lbl_endpoints_sec = QLabel(self.tr("CONNEXION & SÉCURITÉ"))
        lbl_endpoints_sec.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: 700; letter-spacing: 0.5px; background: transparent; border: none;")
        endpoints_layout.addWidget(lbl_endpoints_sec)

        # Ligne Streamable HTTP
        row_http = QHBoxLayout()
        row_http.setSpacing(8)
        lbl_http_title = QLabel(self.tr("Streamable HTTP :"))
        lbl_http_title.setMinimumWidth(130)
        lbl_http_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: 500; background: transparent; border: none;")
        row_http.addWidget(lbl_http_title)

        self.edit_url_http = self._create_readonly_line_edit(self.url, "mcp_edit_url_http")
        row_http.addWidget(self.edit_url_http, 1)

        self.btn_copy_url_http = SecondaryButton(self.tr("Copier"))
        self.btn_copy_url_http.setIcon(load_phosphor_icon("ph.copy", color=DesignTokens.TEXT_PRIMARY))
        self.btn_copy_url_http.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_copy_url_http.setToolTip(self.tr("Copier l'URL Streamable HTTP (/mcp)"))
        apply_compact_style(self.btn_copy_url_http, height=30)
        self.btn_copy_url_http.clicked.connect(self.copy_url)
        row_http.addWidget(self.btn_copy_url_http)
        endpoints_layout.addLayout(row_http)

        # Ligne SSE legacy
        row_sse = QHBoxLayout()
        row_sse.setSpacing(8)
        lbl_sse_title = QLabel(self.tr("Endpoint SSE :"))
        lbl_sse_title.setMinimumWidth(130)
        lbl_sse_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: 500; background: transparent; border: none;")
        row_sse.addWidget(lbl_sse_title)

        self.edit_url_sse = self._create_readonly_line_edit(self.sse_url, "mcp_edit_url_sse")
        row_sse.addWidget(self.edit_url_sse, 1)

        self.btn_copy_url_sse = SecondaryButton(self.tr("Copier"))
        self.btn_copy_url_sse.setIcon(load_phosphor_icon("ph.copy", color=DesignTokens.TEXT_PRIMARY))
        self.btn_copy_url_sse.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_copy_url_sse.setToolTip(self.tr("Copier l'URL du flux SSE (/sse)"))
        apply_compact_style(self.btn_copy_url_sse, height=30)
        self.btn_copy_url_sse.clicked.connect(self.copy_sse_url)
        row_sse.addWidget(self.btn_copy_url_sse)
        endpoints_layout.addLayout(row_sse)

        # Ligne Jeton Bearer avec bouton Renouveler rattaché
        row_token = QHBoxLayout()
        row_token.setSpacing(8)
        lbl_token_title = QLabel(self.tr("Jeton Bearer :"))
        lbl_token_title.setMinimumWidth(130)
        lbl_token_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: 500; background: transparent; border: none;")
        row_token.addWidget(lbl_token_title)

        self.edit_token = self._create_readonly_line_edit("••••••••••••••••••••••••", "mcp_edit_token")
        row_token.addWidget(self.edit_token, 1)

        self.btn_toggle_token = IconButton("ph.eye", tooltip=self.tr("Afficher ou masquer le jeton"), size=24)
        self.btn_toggle_token.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_token.clicked.connect(self.toggle_token_visibility)
        row_token.addWidget(self.btn_toggle_token)

        self.btn_copy_token = SecondaryButton(self.tr("Copier"))
        self.btn_copy_token.setIcon(load_phosphor_icon("ph.copy", color=DesignTokens.TEXT_PRIMARY))
        self.btn_copy_token.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_copy_token.setToolTip(self.tr("Copier le jeton secret dans le presse-papiers"))
        apply_compact_style(self.btn_copy_token, height=30)
        self.btn_copy_token.clicked.connect(self.copy_token)
        row_token.addWidget(self.btn_copy_token)

        self.btn_rotate_token = SecondaryButton(self.tr("Renouveler"))
        self.btn_rotate_token.setIcon(load_phosphor_icon("ph.arrows-clockwise", color=DesignTokens.TEXT_PRIMARY))
        self.btn_rotate_token.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_rotate_token.setToolTip(self.tr("Générer un nouveau jeton Bearer aléatoire. Invalide immédiatement les sessions des agents connectés."))
        apply_compact_style(self.btn_rotate_token, height=30)
        self.btn_rotate_token.clicked.connect(self._handle_rotate_token_requested)
        row_token.addWidget(self.btn_rotate_token)
        endpoints_layout.addLayout(row_token)

        # Ligne de raccourcis rapides d'exportation
        row_quick_exports = QHBoxLayout()
        row_quick_exports.setSpacing(8)
        lbl_exports_title = QLabel(self.tr("Raccourcis :"))
        lbl_exports_title.setMinimumWidth(130)
        lbl_exports_title.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11.5px; background: transparent; border: none;")
        row_quick_exports.addWidget(lbl_exports_title)

        self.btn_copy_env_export = SecondaryButton(self.tr("Export Shell (ENV)"))
        self.btn_copy_env_export.setIcon(load_phosphor_icon("ph.terminal", color=DesignTokens.TEXT_PRIMARY))
        self.btn_copy_env_export.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_copy_env_export.setToolTip(self.tr("Copier la variable d'environnement shell 'export ANKIFORGE_MCP_TOKEN=...'"))
        apply_compact_style(self.btn_copy_env_export, height=28)
        self.btn_copy_env_export.clicked.connect(self.copy_env_export)
        row_quick_exports.addWidget(self.btn_copy_env_export)

        self.btn_copy_auth_url = SecondaryButton(self.tr("URL avec Jeton"))
        self.btn_copy_auth_url.setIcon(load_phosphor_icon("ph.link", color=DesignTokens.TEXT_PRIMARY))
        self.btn_copy_auth_url.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_copy_auth_url.setToolTip(self.tr("Copier l'URL complète incluant le jeton en paramètre de requête pour les clients compatibles"))
        apply_compact_style(self.btn_copy_auth_url, height=28)
        self.btn_copy_auth_url.clicked.connect(self.copy_authenticated_url)
        row_quick_exports.addWidget(self.btn_copy_auth_url)
        row_quick_exports.addStretch()

        endpoints_layout.addLayout(row_quick_exports)

        col_left.addWidget(self.card_endpoints)
        col_left.addStretch()
        columns_layout.addLayout(col_left, 1)

        # ── Colonne Droite : Configurations Clients Prêtes à l'Emploi ─────
        col_right = QVBoxLayout()
        col_right.setSpacing(14)

        self.card_snippets = self._create_card("mcp_card_snippets")
        snippets_layout = QVBoxLayout(self.card_snippets)
        snippets_layout.setContentsMargins(16, 14, 16, 14)
        snippets_layout.setSpacing(10)

        header_snippets_row = QHBoxLayout()
        lbl_snippets_sec = QLabel(self.tr("CONFIGURATIONS CLIENTS PRÊTES À L'EMPLOI"))
        lbl_snippets_sec.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: 700; letter-spacing: 0.5px; background: transparent; border: none;")
        lbl_snippets_sec.setWordWrap(True)
        header_snippets_row.addWidget(lbl_snippets_sec)
        header_snippets_row.addStretch()

        self.btn_copy_snippet = PrimaryButton(self.tr("Copier la configuration"))
        self.btn_copy_snippet.setIcon(load_phosphor_icon("ph.copy", color=DesignTokens.TEXT_ON_ACCENT))
        self.btn_copy_snippet.setCursor(Qt.CursorShape.PointingHandCursor)
        apply_compact_style(self.btn_copy_snippet, height=30)
        self.btn_copy_snippet.clicked.connect(self.copy_current_snippet)
        header_snippets_row.addWidget(self.btn_copy_snippet)
        snippets_layout.addLayout(header_snippets_row)

        self.tab_bar_clients = SegmentedTabBar(variant="subtab", parent=self)
        self.tab_bar_clients.setObjectName("mcp_tab_bar_clients")
        btn_claude = self.tab_bar_clients.add_tab("claude", self.tr("Claude"), icon_name="ph.app-window")
        btn_agy = self.tab_bar_clients.add_tab("agy", self.tr("Antigravity (agy)"), icon_name="ph.terminal")
        btn_cursor = self.tab_bar_clients.add_tab("cursor", self.tr("Cursor"), icon_name="ph.cursor")
        btn_curl = self.tab_bar_clients.add_tab("curl", self.tr("cURL"), icon_name="ph.terminal-window")
        btn_claude.setAccessibleName(self.tr("Onglet configuration Claude Desktop et Code"))
        btn_agy.setAccessibleName(self.tr("Onglet configuration Antigravity CLI"))
        btn_cursor.setAccessibleName(self.tr("Onglet configuration Cursor et Windsurf"))
        btn_curl.setAccessibleName(self.tr("Onglet configuration cURL et CLI"))
        btn_claude.setToolTip(self.tr("Claude (Desktop & Code)"))
        btn_agy.setToolTip(self.tr("Antigravity CLI (agy)"))
        btn_cursor.setToolTip(self.tr("Cursor / Windsurf"))
        btn_curl.setToolTip(self.tr("cURL / CLI"))
        self.tab_bar_clients.tab_index_changed.connect(self._on_client_tab_changed)
        snippets_layout.addWidget(self.tab_bar_clients)

        # Ligne d'aide contextuelle avec bouton Ouvrir le fichier
        row_hint = QHBoxLayout()
        row_hint.setSpacing(8)

        self.lbl_snippet_hint = QLabel(self.tr("Collez ce bloc dans votre fichier claude_desktop_config.json :"))
        self.lbl_snippet_hint.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 12px; background: transparent; border: none;")
        self.lbl_snippet_hint.setWordWrap(True)
        row_hint.addWidget(self.lbl_snippet_hint, 1)

        self.btn_open_client_config = SecondaryButton(self.tr("Ouvrir le fichier"))
        self.btn_open_client_config.setIcon(load_phosphor_icon("ph.arrow-square-out", color=DesignTokens.TEXT_PRIMARY))
        self.btn_open_client_config.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_open_client_config.setToolTip(self.tr("Ouvrir directement le fichier de configuration cible dans l'éditeur système"))
        apply_compact_style(self.btn_open_client_config, height=26)
        self.btn_open_client_config.clicked.connect(self.open_client_config)
        row_hint.addWidget(self.btn_open_client_config)

        snippets_layout.addLayout(row_hint)

        self.edit_snippet_code = QPlainTextEdit()
        self.edit_snippet_code.setObjectName("mcp_edit_snippet_code")
        self.edit_snippet_code.setReadOnly(True)
        self.edit_snippet_code.setMinimumHeight(170)
        self.edit_snippet_code.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.edit_snippet_code.setStyleSheet(f"""
            QPlainTextEdit#mcp_edit_snippet_code {{
                background-color: {DesignTokens.BG_INPUT};
                color: {DesignTokens.TEXT_PRIMARY};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
                font-family: {DesignTokens.FONT_CODE};
                font-size: 12px;
                padding: 10px;
            }}
        """)
        font = QFont(DesignTokens.FONT_CODE)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.edit_snippet_code.setFont(font)
        snippets_layout.addWidget(self.edit_snippet_code)

        # Note de bas de carte sobre
        lbl_tip = QLabel(self.tr("Astuce : L'intégration MCP délègue l'exécution à votre agent externe habituel sans consommer de quota LLM dans AnkiForge."))
        lbl_tip.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; background: transparent; border: none;")
        lbl_tip.setWordWrap(True)
        snippets_layout.addWidget(lbl_tip)

        col_right.addWidget(self.card_snippets)
        columns_layout.addLayout(col_right, 1)

        root_layout.addLayout(columns_layout, 1)
        self._refresh_snippet_view()

    def _create_card(self, object_name: str) -> QFrame:
        card = QFrame()
        card.setObjectName(object_name)
        card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        card.setStyleSheet(f"""
            QFrame#{object_name} {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 8px;
            }}
            QFrame#{object_name} QLabel {{
                border: none;
                background: transparent;
            }}
        """)
        return card

    def _create_kpi_box(self, icon_name: str, title: str, initial_value: str) -> tuple[QFrame, QLabel]:
        box = QFrame()
        box.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 8px 10px;
            }}
            QLabel {{
                border: none;
                background: transparent;
            }}
        """)
        box_layout = QVBoxLayout(box)
        box_layout.setContentsMargins(6, 6, 6, 6)
        box_layout.setSpacing(3)

        top_row = QHBoxLayout()
        top_row.setSpacing(6)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(load_phosphor_icon(icon_name, color=DesignTokens.TEXT_MUTED).pixmap(14, 14))
        top_row.addWidget(icon_lbl)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: 500;")
        top_row.addWidget(title_lbl)
        top_row.addStretch()
        box_layout.addLayout(top_row)

        val_lbl = QLabel(initial_value)
        val_lbl.setObjectName("kpi_value")
        val_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 13px; font-weight: 700;")
        box_layout.addWidget(val_lbl)

        return box, val_lbl

    def _create_readonly_line_edit(self, text: str, object_name: str = "") -> QLineEdit:
        line_edit = QLineEdit(text)
        if object_name:
            line_edit.setObjectName(object_name)
        line_edit.setReadOnly(True)
        line_edit.setFixedHeight(30)
        sel = f"QLineEdit#{object_name}" if object_name else "QLineEdit"
        line_edit.setStyleSheet(f"""
            {sel} {{
                background-color: {DesignTokens.BG_INPUT};
                color: {DesignTokens.TEXT_PRIMARY};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
                font-family: {DesignTokens.FONT_CODE};
                font-size: 12px;
                padding: 4px 8px;
            }}
        """)
        return line_edit

    def set_status(
        self,
        status: str,
        port: int | None = None,
        token: str | None = None,
        message: str = "",
    ) -> None:
        """Met à jour l'état du serveur MCP sur le cockpit."""
        self._status = status
        if port is not None:
            self._port = port
        if token is not None:
            self._token = token

        is_running = self._status == "running"
        is_mutating = self._status == "mutating"
        self.btn_start.setEnabled(not is_running and not is_mutating)
        self.btn_stop.setEnabled(is_running)
        self.btn_restart.setEnabled(is_running)
        self.btn_rotate_token.setEnabled(True)
        self.btn_ping.setEnabled(is_running)

        # Couleurs sémantiques des icônes selon leur état actif / désactivé
        start_icon_col = DesignTokens.COLOR_GREEN if self.btn_start.isEnabled() else DesignTokens.TEXT_MUTED
        stop_icon_col = DesignTokens.COLOR_RED if self.btn_stop.isEnabled() else DesignTokens.TEXT_MUTED
        restart_icon_col = DesignTokens.COLOR_YELLOW if self.btn_restart.isEnabled() else DesignTokens.TEXT_MUTED

        self.btn_start.setIcon(load_phosphor_icon("ph.play", color=start_icon_col))
        self.btn_stop.setIcon(load_phosphor_icon("ph.stop", color=stop_icon_col))
        self.btn_restart.setIcon(load_phosphor_icon("ph.arrows-clockwise", color=restart_icon_col))

        if is_running:
            if self._started_at is None:
                self._started_at = datetime.now()
            if not self._uptime_timer.isActive():
                self._uptime_timer.start()
            self._update_uptime_display()
            self.status_badge.setText(self.tr("Actif"))
            self.status_badge.set_variant("success")
        else:
            self._started_at = None
            if self._uptime_timer.isActive():
                self._uptime_timer.stop()
            self.lbl_uptime.setText(self.tr("Uptime : —"))
            self.lbl_ping_result.setText("")

            if self._status == "error":
                self.status_badge.setText(self.tr("Erreur"))
                self.status_badge.set_variant("danger")
            elif self._status == "mutating":
                self.status_badge.setText(self.tr("Mutation..."))
                self.status_badge.set_variant("warning")
            else:
                self.status_badge.setText(self.tr("Arrêté"))
                self.status_badge.set_variant("neutral")

        self.lbl_port_info.setText(tr("Port : %1", self._port))
        self.edit_url_http.setText(self.url)
        self.edit_url_sse.setText(self.sse_url)
        self._update_token_display()
        self._refresh_snippet_view()

    def _update_uptime_display(self) -> None:
        if self._started_at and self._status == "running":
            delta = datetime.now() - self._started_at
            total_seconds = max(0, int(delta.total_seconds()))
            hours, remainder = divmod(total_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            if hours > 0:
                uptime_str = f"{hours}h {minutes:02d}m"
            elif minutes > 0:
                uptime_str = f"{minutes}m {seconds:02d}s"
            else:
                uptime_str = f"{seconds}s"
            self.lbl_uptime.setText(tr("Uptime : %1", uptime_str))
        else:
            self.lbl_uptime.setText(self.tr("Uptime : —"))

    def _update_token_display(self) -> None:
        if self._token_visible:
            self.edit_token.setText(self._token or "")
        else:
            if self._token and len(self._token) >= 12:
                prefix = self._token[:6]
                self.edit_token.setText(f"{prefix}...••••••••••••")
            elif self._token:
                self.edit_token.setText("••••••••••••••••••••••••")
            else:
                self.edit_token.setText("")

    def toggle_token_visibility(self) -> None:
        self._token_visible = not self._token_visible
        self._update_token_display()
        icon_name = "ph.eye-slash" if self._token_visible else "ph.eye"
        self.btn_toggle_token.setIcon(load_phosphor_icon(icon_name, color=DesignTokens.TEXT_PRIMARY))

    def _flash_button(self, btn: QPushButton, original_text: str, original_icon_name: str) -> None:
        """Fournit un retour tactile et visuel temporaire (1.5s) de confirmation de copie."""
        btn.setText(self.tr("Copié !"))
        btn.setIcon(load_phosphor_icon("ph.check", color=DesignTokens.COLOR_GREEN))
        timer = QTimer(btn)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: self._reset_button(btn, original_text, original_icon_name))
        timer.start(1500)

    def _reset_button(self, btn: QPushButton, text: str, icon_name: str) -> None:
        try:
            import shiboken6

            if not shiboken6.isValid(btn):
                return
            btn.setText(text)
            is_primary = isinstance(btn, PrimaryButton)
            icon_col = DesignTokens.TEXT_ON_ACCENT if is_primary else DesignTokens.TEXT_PRIMARY
            btn.setIcon(load_phosphor_icon(icon_name, color=icon_col))
        except Exception:
            pass

    def copy_url(self) -> None:
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self.url)
            self._flash_button(self.btn_copy_url_http, self.tr("Copier"), "ph.copy")
            show_toast(self, tr("URL Streamable HTTP copiée : %1", self.url))

    def copy_sse_url(self) -> None:
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self.sse_url)
            self._flash_button(self.btn_copy_url_sse, self.tr("Copier"), "ph.copy")
            show_toast(self, tr("URL SSE copiée : %1", self.sse_url))

    def copy_token(self) -> None:
        if not self._token:
            self._load_token_from_disk()
        if self._token:
            clipboard = QGuiApplication.clipboard()
            if clipboard is not None:
                clipboard.setText(self._token)
                self._flash_button(self.btn_copy_token, self.tr("Copier"), "ph.copy")
                show_toast(self, self.tr("Jeton Bearer copié dans le presse-papiers."))

    def copy_env_export(self) -> None:
        if not self._token:
            self._load_token_from_disk()
        token = self._token or "VOTRE_JETON_BEARER"
        export_cmd = f"export ANKIFORGE_MCP_TOKEN={token}"
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(export_cmd)
            self._flash_button(self.btn_copy_env_export, self.tr("Export Shell (ENV)"), "ph.terminal")
            show_toast(self, self.tr("Commande export ANKIFORGE_MCP_TOKEN copiée."))

    def copy_authenticated_url(self) -> None:
        if not self._token:
            self._load_token_from_disk()
        token = self._token or "VOTRE_JETON_BEARER"
        auth_url = f"{self.url}?token={token}"
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(auth_url)
            self._flash_button(self.btn_copy_auth_url, self.tr("URL avec Jeton"), "ph.link")
            show_toast(self, self.tr("URL avec jeton d'authentification copiée."))

    def _handle_rotate_token_requested(self) -> None:
        self.rotate_token_requested.emit()
        show_toast(self, self.tr("Renouvellement du jeton demandé. Pensez à actualiser vos configurations clientes."))

    def test_connection_ping(self) -> None:
        """Sonde le serveur MCP local en arrière-plan et affiche la latence en millisecondes."""
        if self._status != "running":
            self.lbl_ping_result.setText(self.tr("Serveur arrêté"))
            self.lbl_ping_result.setStyleSheet(f"color: {DesignTokens.COLOR_YELLOW}; font-size: 11px;")
            return

        self.btn_ping.setEnabled(False)
        self.lbl_ping_result.setText(self.tr("Test en cours..."))
        self.lbl_ping_result.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")

        target_url = self.url
        auth_token = self._token or ""

        def _worker() -> None:
            t0 = time.perf_counter()
            req = urllib.request.Request(
                target_url,
                headers={"Authorization": f"Bearer {auth_token}"},
                method="GET",
            )
            status_ok = False
            status_msg = ""
            try:
                with urllib.request.urlopen(req, timeout=1.5):  # nosec B310  # sonde locale sur 127.0.0.1 avec timeout borné
                    elapsed_ms = int((time.perf_counter() - t0) * 1000)
                    status_ok = True
                    status_msg = f"🟢 200 OK ({elapsed_ms}ms)"
            except urllib.error.HTTPError as exc:
                elapsed_ms = int((time.perf_counter() - t0) * 1000)
                status_ok = True
                status_msg = f"🟢 En ligne ({elapsed_ms}ms - HTTP {exc.code})"
            except Exception as exc:
                status_ok = False
                status_msg = f"🔴 Inaccessible ({exc.__class__.__name__})"

            self.ping_finished.emit(status_ok, status_msg)

        threading.Thread(target=_worker, daemon=True).start()

    def _on_ping_finished(self, status_ok: bool, status_msg: str) -> None:
        self.btn_ping.setEnabled(self._status == "running")
        color = DesignTokens.COLOR_GREEN if status_ok else DesignTokens.COLOR_RED
        self.lbl_ping_result.setText(status_msg)
        self.lbl_ping_result.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: 600; background: transparent; border: none;")

    def _init_activity_tracker_listener(self) -> None:
        """Écoute la télémétrie des appels d'outils MCP pour rafraîchir les mini-KPIs."""
        try:
            from ankiforge.services.ai.mcp_tracker import get_mcp_activity_tracker

            tracker = get_mcp_activity_tracker()
            tracker.signals.activity_started.connect(self._on_activity_event)
            tracker.signals.activity_updated.connect(self._on_activity_event)
            tracker.signals.history_cleared.connect(self._on_activity_cleared)

            total = tracker.total_calls if isinstance(tracker.total_calls, int) else tracker.total_calls()
            if hasattr(self, "lbl_kpi_calls") and self.lbl_kpi_calls:
                self.lbl_kpi_calls.setText(str(total))
            history = tracker.get_history()
            if history and hasattr(self, "lbl_kpi_last_tool") and self.lbl_kpi_last_tool:
                self.lbl_kpi_last_tool.setText(history[-1].tool_name)
        except Exception as exc:
            logger.debug("Télémétrie d'activité MCP non initialisée : %s", exc)

    def _on_activity_event(self, data: dict[str, Any]) -> None:
        try:
            from ankiforge.services.ai.mcp_tracker import get_mcp_activity_tracker

            tracker = get_mcp_activity_tracker()
            if hasattr(self, "lbl_kpi_calls") and self.lbl_kpi_calls:
                calls = tracker.total_calls if isinstance(tracker.total_calls, int) else tracker.total_calls()
                self.lbl_kpi_calls.setText(str(calls))
            tool_name = str(data.get("tool_name", ""))
            if tool_name and hasattr(self, "lbl_kpi_last_tool") and self.lbl_kpi_last_tool:
                self.lbl_kpi_last_tool.setText(tool_name)
        except Exception as exc:
            logger.debug("Erreur rafraîchissement KPI MCP : %s", exc)

    def _on_activity_cleared(self) -> None:
        if hasattr(self, "lbl_kpi_calls") and self.lbl_kpi_calls:
            self.lbl_kpi_calls.setText("0")
        if hasattr(self, "lbl_kpi_last_tool") and self.lbl_kpi_last_tool:
            self.lbl_kpi_last_tool.setText(self.tr("Aucun appel"))

    def _on_client_tab_changed(self, index: int) -> None:
        mapping = {0: "claude", 1: "agy", 2: "cursor", 3: "curl"}
        self._active_snippet_key = mapping.get(index, "claude")
        self._refresh_snippet_view()

    def _get_client_config_path(self, client: str) -> Path | None:
        if client == "claude":
            if sys.platform == "darwin":
                return Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
            elif sys.platform == "win32":
                appdata = os.environ.get("APPDATA")
                return Path(appdata) / "Claude" / "claude_desktop_config.json" if appdata else None
            else:
                return Path.home() / ".config" / "claude" / "claude_desktop_config.json"
        elif client == "agy":
            return Path.home() / ".gemini" / "antigravity-cli" / "mcp" / "ankiforge.json"
        elif client == "cursor":
            project_cursor = Path.cwd() / ".cursor" / "mcp.json"
            if project_cursor.parent.exists():
                return project_cursor
            return Path.home() / ".cursor" / "mcp.json"
        return None

    def open_client_config(self) -> None:
        """Ouvre le fichier de configuration correspondant au client sélectionné dans l'éditeur système."""
        target_path = self._get_client_config_path(self._active_snippet_key)
        if not target_path:
            show_toast(self, self.tr("Aucun fichier de configuration requis pour ce mode (commande directe en terminal)."))
            return

        try:
            if not target_path.exists():
                target_path.parent.mkdir(parents=True, exist_ok=True)
                target_path.write_text(self.get_snippet_config(self._active_snippet_key), encoding="utf-8")
                show_toast(self, tr("Fichier de configuration créé : %1", target_path.name))

            opened = QDesktopServices.openUrl(QUrl.fromLocalFile(str(target_path)))
            if not opened:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(target_path.parent)))
                show_toast(self, tr("Dossier ouvert dans le gestionnaire : %1", target_path.parent.name))
            else:
                show_toast(self, tr("Fichier ouvert : %1", target_path.name))
        except Exception as exc:
            logger.warning("Échec d'ouverture du fichier de configuration client %s : %s", target_path, exc)
            show_toast(self, tr("Impossible d'ouvrir le fichier : %1", str(exc)))

    def get_snippet_config(self, client: str) -> str:
        """Génère le texte de configuration formaté pour le client spécifié."""
        token = self._token or "VOTRE_JETON_BEARER"
        if client == "claude":
            claude_cfg: dict[str, Any] = {
                "mcpServers": {
                    "ankiforge": {
                        "url": self.url,
                        "headers": {
                            "Authorization": f"Bearer {token}",
                        },
                    }
                }
            }
            return json.dumps(claude_cfg, indent=2, ensure_ascii=False)
        elif client == "agy":
            agy_cfg: dict[str, Any] = {
                "name": "ankiforge",
                "url": self.url,
                "headers": {
                    "Authorization": f"Bearer {token}",
                },
            }
            return json.dumps(agy_cfg, indent=2, ensure_ascii=False)
        elif client == "cursor":
            cursor_cfg: dict[str, Any] = {
                "mcpServers": {
                    "ankiforge": {
                        "url": self.url,
                        "headers": {
                            "Authorization": f"Bearer {token}",
                        },
                    }
                }
            }
            return json.dumps(cursor_cfg, indent=2, ensure_ascii=False)
        elif client == "curl":
            return (
                f'curl -X POST "{self.url}" \\\n'
                f'  -H "Authorization: Bearer {token}" \\\n'
                '  -H "Content-Type: application/json" \\\n'
                '  -d \'{"jsonrpc": "2.0", "method": "tools/list", "params": {}, "id": 1}\''
            )
        return ""

    def _refresh_snippet_view(self) -> None:
        hints = {
            "claude": self.tr("Collez ce bloc dans votre fichier claude_desktop_config.json :"),
            "agy": self.tr("Collez ce bloc dans ~/.gemini/antigravity-cli/mcp/ankiforge.json :"),
            "cursor": self.tr("Ajoutez ce serveur dans les paramètres MCP de Cursor (.cursor/mcp.json) :"),
            "curl": self.tr("Commande cURL de test d'interrogation du serveur MCP :"),
        }
        self.lbl_snippet_hint.setText(hints.get(self._active_snippet_key, ""))
        self.edit_snippet_code.setPlainText(self.get_snippet_config(self._active_snippet_key))

        # Afficher ou masquer le bouton 'Ouvrir le fichier' pour le mode cURL (pas de fichier)
        has_file = self._active_snippet_key != "curl"
        self.btn_open_client_config.setVisible(has_file)

    def copy_current_snippet(self) -> None:
        text = self.get_snippet_config(self._active_snippet_key)
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(text)
            self._flash_button(self.btn_copy_snippet, self.tr("Copier la configuration"), "ph.copy")
            show_toast(self, self.tr("Configuration client MCP copiée dans le presse-papiers."))

    def set_pending_request(self, context_item: Any, initial_prompt: str) -> None:
        """Affiche le bandeau d'action rapide pour une demande d'assistance contextuelle externe."""
        self.pending_request = {
            "context_item": context_item,
            "prompt": initial_prompt,
        }
        ctx_desc = str(context_item)
        if isinstance(context_item, dict):
            c_type = context_item.get("type", "ressource")
            c_id = context_item.get("id", "")
            ctx_desc = f"{c_type} #{c_id}" if c_id else c_type

        self.lbl_request_context.setText(tr("Contexte ciblé : %1", ctx_desc))
        self.edit_request_prompt.setPlainText(initial_prompt)
        self.banner_context_request.setVisible(True)

    def _dismiss_pending_request(self) -> None:
        self.pending_request = None
        self.banner_context_request.setVisible(False)

    def _copy_request_prompt(self) -> None:
        if self.pending_request and self.pending_request.get("prompt"):
            clipboard = QGuiApplication.clipboard()
            if clipboard is not None:
                clipboard.setText(str(self.pending_request["prompt"]))
                self._flash_button(
                    self.btn_copy_request_prompt,
                    self.tr("Copier le prompt pour mon agent (CLI / Claude)"),
                    "ph.copy",
                )
                show_toast(self, self.tr("Prompt copié dans le presse-papiers pour votre agent externe !"))

    def _apply_ops_button_styles(self, profile: Any = None) -> None:
        """Applique les styles chromatiques et les micro-affordances sur les boutons d'opération."""
        green = getattr(profile, "color_green", DesignTokens.COLOR_GREEN)
        green_bg = getattr(profile, "color_green_bg", DesignTokens.COLOR_GREEN_BG)
        green_border = getattr(profile, "color_green_border", DesignTokens.COLOR_GREEN_BORDER)
        red = getattr(profile, "color_red", DesignTokens.COLOR_RED)
        red_bg = getattr(profile, "color_red_bg", DesignTokens.COLOR_RED_BG)
        red_border = getattr(profile, "color_red_border", DesignTokens.COLOR_RED_BORDER)
        yellow = getattr(profile, "color_yellow", DesignTokens.COLOR_YELLOW)
        yellow_bg = getattr(profile, "color_yellow_bg", DesignTokens.COLOR_YELLOW_BG)
        yellow_border = getattr(profile, "color_yellow_border", DesignTokens.COLOR_YELLOW_BORDER)
        text_muted = getattr(profile, "text_muted", DesignTokens.TEXT_MUTED)
        border_col = getattr(profile, "border_color", DesignTokens.BORDER_COLOR)

        self.btn_start.setStyleSheet(f"""
            QPushButton#mcp_btn_start {{
                background-color: {green_bg};
                color: {green};
                border: 1px solid {green_border};
                border-radius: {DesignTokens.RADIUS_SM}px;
                font-weight: 600;
                padding: 4px 14px;
            }}
            QPushButton#mcp_btn_start:hover {{
                background-color: rgba(16, 185, 129, 0.28);
                border: 1px solid {green};
            }}
            QPushButton#mcp_btn_start:pressed {{
                background-color: rgba(16, 185, 129, 0.40);
                padding-top: 5px;
            }}
            QPushButton#mcp_btn_start:disabled {{
                background-color: transparent;
                color: {text_muted};
                border: 1px solid {border_col};
            }}
        """)

        self.btn_stop.setStyleSheet(f"""
            QPushButton#mcp_btn_stop {{
                background-color: {red_bg};
                color: {red};
                border: 1px solid {red_border};
                border-radius: {DesignTokens.RADIUS_SM}px;
                font-weight: 600;
                padding: 4px 14px;
            }}
            QPushButton#mcp_btn_stop:hover {{
                background-color: rgba(239, 68, 68, 0.26);
                border: 1px solid {red};
            }}
            QPushButton#mcp_btn_stop:pressed {{
                background-color: rgba(239, 68, 68, 0.38);
                padding-top: 5px;
            }}
            QPushButton#mcp_btn_stop:disabled {{
                background-color: transparent;
                color: {text_muted};
                border: 1px solid {border_col};
            }}
        """)

        self.btn_restart.setStyleSheet(f"""
            QPushButton#mcp_btn_restart {{
                background-color: {yellow_bg};
                color: {yellow};
                border: 1px solid {yellow_border};
                border-radius: {DesignTokens.RADIUS_SM}px;
                font-weight: 600;
                padding: 4px 14px;
            }}
            QPushButton#mcp_btn_restart:hover {{
                background-color: rgba(245, 158, 11, 0.26);
                border: 1px solid {yellow};
            }}
            QPushButton#mcp_btn_restart:pressed {{
                background-color: rgba(245, 158, 11, 0.38);
                padding-top: 5px;
            }}
            QPushButton#mcp_btn_restart:disabled {{
                background-color: transparent;
                color: {text_muted};
                border: 1px solid {border_col};
            }}
        """)

    def refresh_theme(self, profile: Any) -> None:
        """Adapte les styles au profil de thème actif sans cascade de contour parasite."""
        bg_panel = getattr(profile, "bg_panel", DesignTokens.BG_PANEL)
        bg_input = getattr(profile, "bg_input", DesignTokens.BG_INPUT)
        border_color = getattr(profile, "border_color", DesignTokens.BORDER_COLOR)
        text_primary = getattr(profile, "text_primary", DesignTokens.TEXT_PRIMARY)
        text_secondary = getattr(profile, "text_secondary", DesignTokens.TEXT_SECONDARY)
        text_muted = getattr(profile, "text_muted", DesignTokens.TEXT_MUTED)
        accent_primary = getattr(profile, "accent_primary", DesignTokens.ACCENT_PRIMARY)

        card_style_tpl = "QFrame#{name} {{ background-color: {bg}; border: 1px solid {border}; border-radius: 8px; }} QFrame#{name} QLabel {{ border: none; background: transparent; }}"
        banner_style_tpl = (
            "QFrame#{name} {{ background-color: {bg}; border: 1px solid {border}; "
            "border-left: 3px solid {accent}; border-radius: 8px; padding: 10px; }} "
            "QFrame#{name} QLabel {{ border: none; background: transparent; }}"
        )

        if hasattr(self, "card_header"):
            self.card_header.setStyleSheet(card_style_tpl.format(name="mcp_card_header", bg=bg_panel, border=border_color))
        if hasattr(self, "card_lifecycle"):
            self.card_lifecycle.setStyleSheet(card_style_tpl.format(name="mcp_card_lifecycle", bg=bg_panel, border=border_color))
        if hasattr(self, "card_endpoints"):
            self.card_endpoints.setStyleSheet(card_style_tpl.format(name="mcp_card_endpoints", bg=bg_panel, border=border_color))
        if hasattr(self, "card_snippets"):
            self.card_snippets.setStyleSheet(card_style_tpl.format(name="mcp_card_snippets", bg=bg_panel, border=border_color))
        if hasattr(self, "banner_context_request"):
            self.banner_context_request.setStyleSheet(banner_style_tpl.format(name="mcp_banner_context_request", bg=bg_panel, border=border_color, accent=accent_primary))
        if hasattr(self, "edit_snippet_code"):
            self.edit_snippet_code.setStyleSheet(
                f"QPlainTextEdit#mcp_edit_snippet_code {{ background-color: {bg_input}; color: {text_primary}; "
                f"border: 1px solid {border_color}; border-radius: 6px; font-family: {DesignTokens.FONT_CODE}; font-size: 12px; padding: 10px; }}"
            )
        if hasattr(self, "edit_request_prompt"):
            self.edit_request_prompt.setStyleSheet(
                f"QPlainTextEdit#mcp_edit_request_prompt {{ background-color: {bg_input}; color: {text_primary}; "
                f"border: 1px solid {border_color}; border-radius: 6px; font-family: {DesignTokens.FONT_CODE}; font-size: 11.5px; padding: 6px; }}"
            )

        line_edit_style = (
            f"QLineEdit {{ background-color: {bg_input}; color: {text_primary}; "
            f"border: 1px solid {border_color}; border-radius: 6px; padding: 4px 8px; "
            f"font-family: {DesignTokens.FONT_CODE}; font-size: 11.5px; }}"
        )
        if hasattr(self, "edit_url_http"):
            self.edit_url_http.setStyleSheet(line_edit_style)
        if hasattr(self, "edit_url_sse"):
            self.edit_url_sse.setStyleSheet(line_edit_style)
        if hasattr(self, "edit_token"):
            self.edit_token.setStyleSheet(line_edit_style)

        if hasattr(self, "lbl_port_info"):
            self.lbl_port_info.setStyleSheet(f"color: {text_primary}; font-size: 12px; font-weight: 600; background: transparent; border: none;")
        if hasattr(self, "lbl_transport_info"):
            self.lbl_transport_info.setStyleSheet(f"color: {text_muted}; font-size: 12px; background: transparent; border: none;")
        if hasattr(self, "lbl_uptime"):
            self.lbl_uptime.setStyleSheet(f"color: {text_muted}; font-size: 12px; background: transparent; border: none;")
        if hasattr(self, "lbl_snippet_hint"):
            self.lbl_snippet_hint.setStyleSheet(f"color: {text_secondary}; font-size: 12px; background: transparent; border: none;")

        if hasattr(self, "tab_bar_clients") and hasattr(self.tab_bar_clients, "refresh_theme"):
            self.tab_bar_clients.refresh_theme(profile)
        if hasattr(self, "status_badge") and hasattr(self.status_badge, "refresh_theme"):
            self.status_badge.refresh_theme(profile)
        self._apply_ops_button_styles(profile)


__all__ = ["MCPSupervisionWidget"]

"""
Tableau de bord autonome et interactif du serveur MCP local (Model Context Protocol).

Hébergé en tant qu'onglet de premier niveau dans la vue MCP & Agents.
Permet la supervision en direct, le pilotage de cycle de vie (start/stop/restart/rotate),
l'inspection des points de terminaison (Streamable HTTP 2.x et SSE legacy), la génération
de snippets de configuration client prêts à copier (Claude, agy, Cursor, cURL) et la réception
de demandes d'assistance contextuelles externes.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QScrollArea,
    QSizePolicy,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from ankiforge.ui.components.badges import Badge
from ankiforge.ui.components.buttons import IconButton, PrimaryButton, SecondaryButton
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.i18n import tr
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class MCPServerDashboardWidget(QWidget):
    """Tableau de bord opérationnel du serveur MCP local."""

    start_requested = Signal()
    stop_requested = Signal()
    restart_requested = Signal()
    rotate_token_requested = Signal()
    open_preferences_requested = Signal()

    def __init__(
        self,
        initial_status: str = "stopped",
        initial_port: int = 8765,
        initial_token: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("MCPServerDashboardWidget")

        self._status = initial_status
        self._port = initial_port
        self._host = "127.0.0.1"
        self._token = initial_token
        self._token_visible = False
        self._active_snippet_key = "claude"
        self.pending_request: dict[str, Any] | None = None

        if self._token is None:
            self._load_token_from_disk()

        self._setup_ui()
        self.set_status(initial_status, port=initial_port, token=self._token)

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
        from ankiforge.services.ai.mcp_daemon import read_daemon_state
        from ankiforge.utils.paths import get_app_data_dir

        state_file = get_app_data_dir() / "mcp_server.json"
        state = read_daemon_state(state_file)
        if state and state.get("token"):
            self._token = str(state["token"])

    def _setup_ui(self) -> None:
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("background: transparent;")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(28, 24, 28, 28)
        layout.setSpacing(20)

        # ── 1. Hero / Header ───────────────────────────────────────────────
        header_layout = QVBoxLayout()
        header_layout.setSpacing(6)

        title_row = QHBoxLayout()
        title_row.setSpacing(12)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(load_phosphor_icon("ph.plugs-connected", color=DesignTokens.ACCENT_PRIMARY).pixmap(26, 26))
        title_row.addWidget(icon_lbl)

        lbl_title = QLabel(self.tr("Serveur MCP Local (Model Context Protocol)"))
        lbl_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 20px; font-weight: 700;")
        title_row.addWidget(lbl_title)
        title_row.addStretch()

        self.btn_open_prefs = SecondaryButton(self.tr("Préférences"))
        self.btn_open_prefs.setIcon(load_phosphor_icon("ph.gear", color=DesignTokens.TEXT_SECONDARY))
        self.btn_open_prefs.clicked.connect(self.open_preferences_requested.emit)
        title_row.addWidget(self.btn_open_prefs)

        header_layout.addLayout(title_row)

        lbl_subtitle = QLabel(
            self.tr(
                "Exposez les outils d'AnkiForge à vos agents autonomes externes (Claude Code, Antigravity CLI, Cursor). "
                "Le raisonnement et les coûts d'API sont entièrement pris en charge par votre agent sans surcoût dans AnkiForge."
            )
        )
        lbl_subtitle.setWordWrap(True)
        lbl_subtitle.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 13px; line-height: 1.4;")
        header_layout.addWidget(lbl_subtitle)
        layout.addLayout(header_layout)

        # ── 2. Bandeau Requête Contextuelle Externe (Masqué par défaut) ────
        self.banner_context_request = QFrame()
        self.banner_context_request.setObjectName("mcp_banner_context_request")
        self.banner_context_request.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.banner_context_request.setVisible(False)
        self.banner_context_request.setStyleSheet(f"""
            QFrame#mcp_banner_context_request {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.ACCENT_PRIMARY};
                border-radius: 8px;
                padding: 12px;
            }}
            QFrame#mcp_banner_context_request QLabel {{
                border: none;
                background: transparent;
            }}
        """)
        banner_layout = QVBoxLayout(self.banner_context_request)
        banner_layout.setContentsMargins(14, 12, 14, 12)
        banner_layout.setSpacing(10)

        banner_top = QHBoxLayout()
        banner_top.setSpacing(10)

        icon_request = QLabel()
        icon_request.setStyleSheet("background: transparent; border: none;")
        icon_request.setPixmap(load_phosphor_icon("ph.sparkle", color=DesignTokens.ACCENT_PRIMARY).pixmap(18, 18))
        banner_top.addWidget(icon_request)

        lbl_req_title = QLabel(self.tr("Demande d'assistance contextuelle prête pour votre agent externe"))
        lbl_req_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 13px; font-weight: 600; background: transparent; border: none;")
        banner_top.addWidget(lbl_req_title)
        banner_top.addStretch()

        self.btn_dismiss_request = IconButton("ph.x", tooltip=self.tr("Ignorer cette demande"), size=20)
        self.btn_dismiss_request.clicked.connect(self._dismiss_pending_request)
        banner_top.addWidget(self.btn_dismiss_request)
        banner_layout.addLayout(banner_top)

        self.lbl_request_context = QLabel()
        self.lbl_request_context.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11.5px; background: transparent; border: none;")
        banner_layout.addWidget(self.lbl_request_context)

        self.edit_request_prompt = QPlainTextEdit()
        self.edit_request_prompt.setObjectName("mcp_edit_request_prompt")
        self.edit_request_prompt.setReadOnly(True)
        self.edit_request_prompt.setMaximumHeight(80)
        self.edit_request_prompt.setStyleSheet(f"""
            QPlainTextEdit#mcp_edit_request_prompt {{
                background-color: {DesignTokens.BG_MAIN};
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
        self.btn_copy_request_prompt.clicked.connect(self._copy_request_prompt)
        btn_row_req.addWidget(self.btn_copy_request_prompt)

        banner_layout.addLayout(btn_row_req)
        layout.addWidget(self.banner_context_request)

        # ── 3. Carte Supervision & Contrôle de cycle de vie ────────────────
        self.card_lifecycle = self._create_card("mcp_card_lifecycle")
        card_lifecycle_layout = QVBoxLayout(self.card_lifecycle)
        card_lifecycle_layout.setContentsMargins(18, 16, 18, 16)
        card_lifecycle_layout.setSpacing(14)

        top_status_row = QHBoxLayout()
        top_status_row.setSpacing(12)

        lbl_status_caption = QLabel(self.tr("État du serveur :"))
        lbl_status_caption.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 12.5px; font-weight: 600; background: transparent; border: none;")
        top_status_row.addWidget(lbl_status_caption)

        self.status_badge = Badge(self.tr("Inactif"), variant="neutral")
        top_status_row.addWidget(self.status_badge)

        self.lbl_port_info = QLabel(tr("Port : %1", self._port))
        self.lbl_port_info.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 12px; margin-left: 8px; background: transparent; border: none;")
        top_status_row.addWidget(self.lbl_port_info)

        self.lbl_transport_info = QLabel(self.tr("Protocole : Streamable HTTP 2.x + SSE"))
        self.lbl_transport_info.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 12px; margin-left: 8px; background: transparent; border: none;")
        top_status_row.addWidget(self.lbl_transport_info)
        top_status_row.addStretch()

        # Boutons de pilotage
        self.btn_start = PrimaryButton(self.tr("Démarrer"))
        self.btn_start.setIcon(load_phosphor_icon("ph.play", color=DesignTokens.TEXT_ON_ACCENT))
        self.btn_start.clicked.connect(self.start_requested.emit)
        top_status_row.addWidget(self.btn_start)

        self.btn_stop = SecondaryButton(self.tr("Arrêter"))
        self.btn_stop.setIcon(load_phosphor_icon("ph.stop", color=DesignTokens.TEXT_PRIMARY))
        self.btn_stop.clicked.connect(self.stop_requested.emit)
        top_status_row.addWidget(self.btn_stop)

        self.btn_restart = SecondaryButton(self.tr("Redémarrer"))
        self.btn_restart.setIcon(load_phosphor_icon("ph.arrows-clockwise", color=DesignTokens.TEXT_PRIMARY))
        self.btn_restart.clicked.connect(self.restart_requested.emit)
        top_status_row.addWidget(self.btn_restart)

        self.btn_rotate_token = SecondaryButton(self.tr("Renouveler le jeton"))
        self.btn_rotate_token.setIcon(load_phosphor_icon("ph.arrows-clockwise", color=DesignTokens.TEXT_PRIMARY))
        self.btn_rotate_token.clicked.connect(self.rotate_token_requested.emit)
        top_status_row.addWidget(self.btn_rotate_token)

        card_lifecycle_layout.addLayout(top_status_row)
        layout.addWidget(self.card_lifecycle)

        # ── 4. Carte Points de Terminaison & Jeton d'Authentification ───────
        self.card_endpoints = self._create_card("mcp_card_endpoints")
        card_endpoints_layout = QVBoxLayout(self.card_endpoints)
        card_endpoints_layout.setContentsMargins(18, 16, 18, 16)
        card_endpoints_layout.setSpacing(12)

        lbl_endpoints_sec = QLabel(self.tr("CONNEXION & SÉCURITÉ"))
        lbl_endpoints_sec.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: 700; letter-spacing: 0.5px; background: transparent; border: none;")
        card_endpoints_layout.addWidget(lbl_endpoints_sec)

        # Ligne Streamable HTTP
        row_http = QHBoxLayout()
        row_http.setSpacing(10)
        lbl_http_title = QLabel(self.tr("Endpoint Streamable HTTP (Standard MCP) :"))
        lbl_http_title.setMinimumWidth(260)
        lbl_http_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: 500; background: transparent; border: none;")
        row_http.addWidget(lbl_http_title)

        self.edit_url_http = self._create_readonly_line_edit(self.url, "mcp_edit_url_http")
        row_http.addWidget(self.edit_url_http, 1)

        self.btn_copy_url_http = SecondaryButton(self.tr("Copier"))
        self.btn_copy_url_http.setIcon(load_phosphor_icon("ph.copy", color=DesignTokens.TEXT_PRIMARY))
        self.btn_copy_url_http.clicked.connect(self.copy_url)
        row_http.addWidget(self.btn_copy_url_http)
        card_endpoints_layout.addLayout(row_http)

        # Ligne SSE legacy
        row_sse = QHBoxLayout()
        row_sse.setSpacing(10)
        lbl_sse_title = QLabel(self.tr("Endpoint SSE (Legacy) :"))
        lbl_sse_title.setMinimumWidth(260)
        lbl_sse_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: 500; background: transparent; border: none;")
        row_sse.addWidget(lbl_sse_title)

        self.edit_url_sse = self._create_readonly_line_edit(self.sse_url, "mcp_edit_url_sse")
        row_sse.addWidget(self.edit_url_sse, 1)

        self.btn_copy_url_sse = SecondaryButton(self.tr("Copier"))
        self.btn_copy_url_sse.setIcon(load_phosphor_icon("ph.copy", color=DesignTokens.TEXT_PRIMARY))
        self.btn_copy_url_sse.clicked.connect(self.copy_sse_url)
        row_sse.addWidget(self.btn_copy_url_sse)
        card_endpoints_layout.addLayout(row_sse)

        # Ligne Jeton Bearer
        row_token = QHBoxLayout()
        row_token.setSpacing(10)
        lbl_token_title = QLabel(self.tr("Jeton Bearer (256-bit) :"))
        lbl_token_title.setMinimumWidth(260)
        lbl_token_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: 500; background: transparent; border: none;")
        row_token.addWidget(lbl_token_title)

        self.edit_token = self._create_readonly_line_edit("••••••••••••••••••••••••", "mcp_edit_token")
        row_token.addWidget(self.edit_token, 1)

        self.btn_toggle_token = IconButton("ph.eye", tooltip=self.tr("Afficher/Masquer le jeton"), size=24)
        self.btn_toggle_token.clicked.connect(self.toggle_token_visibility)
        row_token.addWidget(self.btn_toggle_token)

        self.btn_copy_token = SecondaryButton(self.tr("Copier"))
        self.btn_copy_token.setIcon(load_phosphor_icon("ph.copy", color=DesignTokens.TEXT_PRIMARY))
        self.btn_copy_token.clicked.connect(self.copy_token)
        row_token.addWidget(self.btn_copy_token)
        card_endpoints_layout.addLayout(row_token)

        layout.addWidget(self.card_endpoints)

        # ── 5. Carte Snippets de Configuration Clients ─────────────────────
        self.card_snippets = self._create_card("mcp_card_snippets")
        card_snippets_layout = QVBoxLayout(self.card_snippets)
        card_snippets_layout.setContentsMargins(18, 16, 18, 16)
        card_snippets_layout.setSpacing(14)

        header_snippets_row = QHBoxLayout()
        lbl_snippets_sec = QLabel(self.tr("CONFIGURATIONS CLIENTS PRÊTES À L'EMPLOI"))
        lbl_snippets_sec.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: 700; letter-spacing: 0.5px; background: transparent; border: none;")
        header_snippets_row.addWidget(lbl_snippets_sec)
        header_snippets_row.addStretch()

        self.btn_copy_snippet = PrimaryButton(self.tr("Copier la configuration"))
        self.btn_copy_snippet.setIcon(load_phosphor_icon("ph.copy", color=DesignTokens.TEXT_ON_ACCENT))
        self.btn_copy_snippet.clicked.connect(self.copy_current_snippet)
        header_snippets_row.addWidget(self.btn_copy_snippet)
        card_snippets_layout.addLayout(header_snippets_row)

        self.tab_bar_clients = QTabBar()
        self.tab_bar_clients.setDrawBase(False)
        self.tab_bar_clients.setStyleSheet("QTabBar { border: none; background: transparent; }")
        self.tab_bar_clients.addTab("Claude (Desktop & Code)")
        self.tab_bar_clients.addTab("Antigravity CLI (agy)")
        self.tab_bar_clients.addTab("Cursor / Windsurf")
        self.tab_bar_clients.addTab("cURL / CLI")
        self.tab_bar_clients.currentChanged.connect(self._on_client_tab_changed)
        card_snippets_layout.addWidget(self.tab_bar_clients)

        self.lbl_snippet_hint = QLabel(self.tr("Collez ce bloc dans votre fichier claude_desktop_config.json :"))
        self.lbl_snippet_hint.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 12px; background: transparent; border: none;")
        card_snippets_layout.addWidget(self.lbl_snippet_hint)

        self.edit_snippet_code = QPlainTextEdit()
        self.edit_snippet_code.setObjectName("mcp_edit_snippet_code")
        self.edit_snippet_code.setReadOnly(True)
        self.edit_snippet_code.setMinimumHeight(140)
        self.edit_snippet_code.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.MinimumExpanding)
        self.edit_snippet_code.setStyleSheet(f"""
            QPlainTextEdit#mcp_edit_snippet_code {{
                background-color: {DesignTokens.BG_MAIN};
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
        card_snippets_layout.addWidget(self.edit_snippet_code)

        layout.addWidget(self.card_snippets)
        layout.addStretch()

        scroll.setWidget(container)
        outer_layout.addWidget(scroll)

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
        """Met à jour l'état du serveur MCP sur le tableau de bord."""
        self._status = status
        if port is not None:
            self._port = port
        if token is not None:
            self._token = token

        # Met à jour les contrôles de cycle de vie
        is_running = self._status == "running"
        is_mutating = self._status == "mutating"
        self.btn_start.setEnabled(not is_running and not is_mutating)
        self.btn_stop.setEnabled(is_running)
        self.btn_restart.setEnabled(is_running)
        self.btn_rotate_token.setEnabled(True)

        # Met à jour le badge d'état
        if self._status == "running":
            self.status_badge.setText(self.tr("Actif"))
            self.status_badge.set_variant("success")
        elif self._status == "error":
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

    def _update_token_display(self) -> None:
        if self._token_visible:
            self.edit_token.setText(self._token or "")
        else:
            self.edit_token.setText("••••••••••••••••••••••••" if self._token else "")

    def toggle_token_visibility(self) -> None:
        self._token_visible = not self._token_visible
        self._update_token_display()
        icon_name = "ph.eye-slash" if self._token_visible else "ph.eye"
        self.btn_toggle_token.setIcon(load_phosphor_icon(icon_name, size=QSize(18, 18)))

    def copy_url(self) -> None:
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self.url)
            show_toast(self, tr("URL Streamable HTTP copiée : %1", self.url))

    def copy_sse_url(self) -> None:
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self.sse_url)
            show_toast(self, tr("URL SSE copiée : %1", self.sse_url))

    def copy_token(self) -> None:
        if not self._token:
            self._load_token_from_disk()
        if self._token:
            clipboard = QGuiApplication.clipboard()
            if clipboard is not None:
                clipboard.setText(self._token)
                show_toast(self, self.tr("Jeton Bearer copié dans le presse-papiers."))

    def _on_client_tab_changed(self, index: int) -> None:
        mapping = {0: "claude", 1: "agy", 2: "cursor", 3: "curl"}
        self._active_snippet_key = mapping.get(index, "claude")
        self._refresh_snippet_view()

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

    def copy_current_snippet(self) -> None:
        text = self.get_snippet_config(self._active_snippet_key)
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(text)
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
                show_toast(self, self.tr("Prompt copié dans le presse-papiers pour votre agent externe !"))

    def refresh_theme(self, profile: Any) -> None:
        """Adapte les styles au profil de thème actif sans cascade de contour parasite."""
        bg_panel = getattr(profile, "bg_panel", DesignTokens.BG_PANEL)
        border_color = getattr(profile, "border_color", DesignTokens.BORDER_COLOR)
        bg_main = getattr(profile, "bg_main", DesignTokens.BG_MAIN)
        text_primary = getattr(profile, "text_primary", DesignTokens.TEXT_PRIMARY)
        accent_primary = getattr(profile, "accent_primary", DesignTokens.ACCENT_PRIMARY)

        card_style_tpl = "QFrame#{name} {{ background-color: {bg}; border: 1px solid {border}; border-radius: 8px; }} QFrame#{name} QLabel {{ border: none; background: transparent; }}"

        if hasattr(self, "card_lifecycle"):
            self.card_lifecycle.setStyleSheet(card_style_tpl.format(name="mcp_card_lifecycle", bg=bg_panel, border=border_color))
        if hasattr(self, "card_endpoints"):
            self.card_endpoints.setStyleSheet(card_style_tpl.format(name="mcp_card_endpoints", bg=bg_panel, border=border_color))
        if hasattr(self, "card_snippets"):
            self.card_snippets.setStyleSheet(card_style_tpl.format(name="mcp_card_snippets", bg=bg_panel, border=border_color))
        if hasattr(self, "banner_context_request"):
            self.banner_context_request.setStyleSheet(card_style_tpl.format(name="mcp_banner_context_request", bg=bg_main, border=accent_primary))
        if hasattr(self, "edit_snippet_code"):
            self.edit_snippet_code.setStyleSheet(
                f"QPlainTextEdit#mcp_edit_snippet_code {{ background-color: {bg_main}; color: {text_primary}; "
                f"border: 1px solid {border_color}; border-radius: 6px; font-family: {DesignTokens.FONT_CODE}; font-size: 12px; padding: 10px; }}"
            )
        if hasattr(self, "edit_request_prompt"):
            self.edit_request_prompt.setStyleSheet(
                f"QPlainTextEdit#mcp_edit_request_prompt {{ background-color: {bg_main}; color: {text_primary}; "
                f"border: 1px solid {border_color}; border-radius: 6px; font-family: {DesignTokens.FONT_CODE}; font-size: 11.5px; padding: 6px; }}"
            )

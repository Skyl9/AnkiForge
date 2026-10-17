"""Tableau de bord autonome et interactif du serveur MCP local (Model Context Protocol).

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
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTabBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ankiforge.services.ai.mcp_tracker import MCPActivityRecord, get_mcp_activity_tracker
from ankiforge.ui.components.badges import Badge, StatusBadge
from ankiforge.ui.components.buttons import IconButton, PrimaryButton, SecondaryButton
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.views.consultant_view.widgets.mcp_garde_fou_widget import MCPGardeFouWidget
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.event_bus import MCPPatchStagedEvent, event_bus
from ankiforge.utils.i18n import tr
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class MCPActivityDetailDialog(QDialog):
    """Dialogue modal d'inspection détaillée d'un appel d'outil MCP."""

    def __init__(self, record: MCPActivityRecord, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("MCPActivityDetailDialog")
        self.setWindowTitle(tr("Détail de l'appel MCP : %1", record.tool_name))
        self.resize(680, 520)
        self._record = record
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # ── En-tête ──
        header_row = QHBoxLayout()
        header_row.setSpacing(10)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(load_phosphor_icon("ph.terminal-window", color=DesignTokens.ACCENT_PRIMARY).pixmap(24, 24))
        header_row.addWidget(icon_lbl)

        lbl_tool = QLabel(self._record.tool_name)
        lbl_tool.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 16px; font-weight: 700; font-family: {DesignTokens.FONT_CODE};")
        header_row.addWidget(lbl_tool)

        header_row.addStretch()

        if self._record.status == "success":
            badge = StatusBadge(self.tr("Succès"), "ph.check-circle", variant="success")
        elif self._record.status == "error":
            badge = StatusBadge(self.tr("Erreur"), "ph.warning-circle", variant="danger")
        else:
            badge = StatusBadge(self.tr("En cours"), "ph.hourglass-simple", variant="warning")
        header_row.addWidget(badge)
        layout.addLayout(header_row)

        # ── Métadonnées (Horodatage & Durée) ──
        meta_row = QHBoxLayout()
        meta_row.setSpacing(16)

        time_str = self._record.started_at.strftime("%H:%M:%S")
        lbl_time = QLabel(tr("Déclenché à : %1", time_str))
        lbl_time.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 12px;")
        meta_row.addWidget(lbl_time)

        if self._record.status != "running":
            dur = self._record.duration_ms
            dur_str = tr("%1 ms", dur) if dur < 1000 else tr("%1 s", round(dur / 1000, 2))
            lbl_dur = QLabel(tr("Durée d'exécution : %1", dur_str))
        else:
            lbl_dur = QLabel(self.tr("En cours d'exécution..."))
        lbl_dur.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 12px;")
        meta_row.addWidget(lbl_dur)
        meta_row.addStretch()
        layout.addLayout(meta_row)

        # ── Arguments ──
        lbl_args = QLabel(self.tr("Paramètres d'appel (Arguments JSON) :"))
        lbl_args.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: 600;")
        layout.addWidget(lbl_args)

        self.edit_args = QPlainTextEdit()
        self.edit_args.setObjectName("mcp_detail_edit_args")
        self.edit_args.setReadOnly(True)
        self.edit_args.setMaximumHeight(140)
        args_json = json.dumps(self._record.args_full, indent=2, ensure_ascii=False) if self._record.args_full else "{}"
        self.edit_args.setPlainText(args_json)
        self.edit_args.setStyleSheet(f"""
            QPlainTextEdit#mcp_detail_edit_args {{
                background-color: {DesignTokens.BG_INPUT};
                color: {DesignTokens.TEXT_PRIMARY};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
                font-family: {DesignTokens.FONT_CODE};
                font-size: 11.5px;
                padding: 8px;
            }}
        """)
        layout.addWidget(self.edit_args)

        # ── Résultat ou Message d'Erreur ──
        res_label_text = self.tr("Message d'erreur :") if self._record.status == "error" else self.tr("Observation / Résultat retourné :")
        lbl_res = QLabel(res_label_text)
        lbl_res.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: 600;")
        layout.addWidget(lbl_res)

        self.edit_result = QPlainTextEdit()
        self.edit_result.setObjectName("mcp_detail_edit_result")
        self.edit_result.setReadOnly(True)
        self.edit_result.setPlainText(self._record.result_full or self.tr("(aucun contenu retourné)"))
        res_color = DesignTokens.COLOR_RED if self._record.status == "error" else DesignTokens.TEXT_PRIMARY
        self.edit_result.setStyleSheet(f"""
            QPlainTextEdit#mcp_detail_edit_result {{
                background-color: {DesignTokens.BG_INPUT};
                color: {res_color};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
                font-family: {DesignTokens.FONT_CODE};
                font-size: 11.5px;
                padding: 8px;
            }}
        """)
        layout.addWidget(self.edit_result, 1)

        # ── Barre de boutons ──
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self.btn_copy_json = SecondaryButton(self.tr("Copier en JSON"))
        self.btn_copy_json.setIcon(load_phosphor_icon("ph.copy", color=DesignTokens.TEXT_PRIMARY))
        self.btn_copy_json.clicked.connect(self._copy_all_json)
        btn_row.addWidget(self.btn_copy_json)

        btn_row.addStretch()

        self.btn_close = PrimaryButton(self.tr("Fermer"))
        self.btn_close.clicked.connect(self.accept)
        btn_row.addWidget(self.btn_close)

        layout.addLayout(btn_row)

    def _copy_all_json(self) -> None:
        data = self._record.to_dict()
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(json.dumps(data, indent=2, ensure_ascii=False))
            show_toast(self, self.tr("Détail de l'appel copié dans le presse-papiers."))


class MCPServerDashboardWidget(QWidget):
    """Tableau de bord opérationnel du serveur MCP local."""

    start_requested = Signal()
    stop_requested = Signal()
    restart_requested = Signal()
    rotate_token_requested = Signal()
    open_preferences_requested = Signal()
    _patch_staged_received = Signal(dict)

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
        self._last_notified_patch_id: str | None = None

        if self._token is None:
            self._load_token_from_disk()

        self._setup_ui()
        self.set_status(initial_status, port=initial_port, token=self._token)

        self._patch_staged_received.connect(self.on_patch_staged)
        event_bus.subscribe(MCPPatchStagedEvent, self._on_mcp_patch_staged_event)

        # Initialisation dynamique de la file du Garde-Fou
        self.garde_fou_widget.reload_pending_patches()

        self._tracker = get_mcp_activity_tracker()
        self._tracker.signals.activity_started.connect(self._on_activity_started)
        self._tracker.signals.activity_updated.connect(self._on_activity_updated)
        self._tracker.signals.history_cleared.connect(self._on_history_cleared)
        self._load_activity_history()

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

        # ── Barre de sous-onglets supérieure ──────────────────────────────
        tab_container = QWidget()
        tab_layout = QHBoxLayout(tab_container)
        tab_layout.setContentsMargins(16, 8, 16, 0)
        tab_layout.setSpacing(0)

        self.sub_tab_bar = QTabBar()
        self.sub_tab_bar.setObjectName("mcp_sub_tab_bar")
        self.sub_tab_bar.setDrawBase(False)
        self.sub_tab_bar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sub_tab_bar.addTab(load_phosphor_icon("ph.sliders", color=DesignTokens.TEXT_SECONDARY), self.tr("Supervision & Configuration"))
        self.sub_tab_bar.addTab(load_phosphor_icon("ph.shield-check", color=DesignTokens.TEXT_SECONDARY), self.tr("Garde-Fou & Validation"))
        self.sub_tab_bar.setStyleSheet(f"""
            QTabBar#mcp_sub_tab_bar {{
                background-color: transparent;
                font-size: 12px;
            }}
            QTabBar#mcp_sub_tab_bar::tab {{
                background-color: transparent;
                color: {DesignTokens.TEXT_SECONDARY};
                padding: 6px 14px;
                border: none;
                border-bottom: 2px solid transparent;
                margin-right: 4px;
                font-weight: 500;
            }}
            QTabBar#mcp_sub_tab_bar::tab:hover {{
                color: {DesignTokens.TEXT_PRIMARY};
                background-color: {DesignTokens.BG_HOVER};
                border-radius: 4px 4px 0 0;
            }}
            QTabBar#mcp_sub_tab_bar::tab:selected {{
                color: {DesignTokens.ACCENT_PRIMARY};
                border-bottom: 2px solid {DesignTokens.ACCENT_PRIMARY};
                font-weight: 600;
            }}
        """)
        self.sub_tab_bar.currentChanged.connect(self._on_sub_tab_changed)
        tab_layout.addWidget(self.sub_tab_bar)
        tab_layout.addStretch()
        outer_layout.addWidget(tab_container)

        tab_separator = QFrame()
        tab_separator.setFixedHeight(1)
        tab_separator.setStyleSheet(f"background-color: {DesignTokens.BORDER_COLOR}; border: none;")
        outer_layout.addWidget(tab_separator)

        # ── Empilement des vues ───────────────────────────────────────────
        self.stacked_widget = QStackedWidget(self)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("background: transparent;")
        self.scroll_supervision = scroll

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

        # ── 6. Carte Activité & Historique des Appels en Temps Réel ────────
        self.card_activity = self._create_card("mcp_card_activity")
        card_activity_layout = QVBoxLayout(self.card_activity)
        card_activity_layout.setContentsMargins(18, 16, 18, 16)
        card_activity_layout.setSpacing(12)

        header_activity_row = QHBoxLayout()
        header_activity_row.setSpacing(10)

        icon_activity = QLabel()
        icon_activity.setPixmap(load_phosphor_icon("ph.clock-counter-clockwise", color=DesignTokens.TEXT_MUTED).pixmap(18, 18))
        header_activity_row.addWidget(icon_activity)

        lbl_activity_sec = QLabel(self.tr("ACTIVITÉ DES OUTILS EN TEMPS RÉEL"))
        lbl_activity_sec.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: 700; letter-spacing: 0.5px; background: transparent; border: none;")
        header_activity_row.addWidget(lbl_activity_sec)

        self.badge_activity_count = Badge(self.tr("0 appel"), variant="neutral")
        header_activity_row.addWidget(self.badge_activity_count)

        header_activity_row.addStretch()

        self.btn_clear_activity = SecondaryButton(self.tr("Vider l'historique"))
        self.btn_clear_activity.setIcon(load_phosphor_icon("ph.trash", color=DesignTokens.TEXT_PRIMARY))
        self.btn_clear_activity.clicked.connect(self.clear_activity_history)
        self.btn_clear_activity.setEnabled(False)
        header_activity_row.addWidget(self.btn_clear_activity)

        card_activity_layout.addLayout(header_activity_row)

        lbl_activity_hint = QLabel(self.tr("Historique en direct des invocations d'outils par vos agents externes. Cliquez sur une ligne pour inspecter les arguments et la réponse."))
        lbl_activity_hint.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 12px; background: transparent; border: none;")
        card_activity_layout.addWidget(lbl_activity_hint)

        self.lbl_empty_activity = QLabel(self.tr("Aucune activité enregistrée. Les appels d'outils de vos agents externes (Claude, Cursor, CLI) apparaîtront ici en temps réel."))
        self.lbl_empty_activity.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_empty_activity.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 12px; padding: 24px; background: transparent; border: none;")
        card_activity_layout.addWidget(self.lbl_empty_activity)

        self.table_activity = QTableWidget()
        self.table_activity.setObjectName("mcp_table_activity")
        self.table_activity.setColumnCount(5)
        self.table_activity.setHorizontalHeaderLabels(
            [
                self.tr("Horodatage"),
                self.tr("Outil"),
                self.tr("Statut"),
                self.tr("Durée"),
                self.tr("Arguments résumés"),
            ]
        )
        self.table_activity.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_activity.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table_activity.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_activity.verticalHeader().setVisible(False)
        self.table_activity.setShowGrid(False)
        self.table_activity.setMinimumHeight(180)
        self.table_activity.setCursor(Qt.CursorShape.PointingHandCursor)
        self.table_activity.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table_activity.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table_activity.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table_activity.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table_activity.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table_activity.cellClicked.connect(self._on_activity_row_clicked)
        self.table_activity.setStyleSheet(f"""
            QTableWidget#mcp_table_activity {{
                background-color: {DesignTokens.BG_MAIN};
                color: {DesignTokens.TEXT_PRIMARY};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
                gridline-color: transparent;
                selection-background-color: {DesignTokens.BG_ACTIVE};
                selection-color: {DesignTokens.TEXT_PRIMARY};
            }}
            QTableWidget#mcp_table_activity::item {{
                padding: 4px 8px;
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
            }}
            QTableWidget#mcp_table_activity::item:selected {{
                background-color: {DesignTokens.BG_ACTIVE};
            }}
            QHeaderView::section {{
                background-color: {DesignTokens.BG_PANEL};
                color: {DesignTokens.TEXT_SECONDARY};
                font-size: 11px;
                font-weight: 600;
                padding: 6px 8px;
                border: none;
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
            }}
        """)
        self.table_activity.setVisible(False)
        card_activity_layout.addWidget(self.table_activity)

        layout.addWidget(self.card_activity)
        layout.addStretch()

        scroll.setWidget(container)
        self.stacked_widget.addWidget(self.scroll_supervision)

        self.garde_fou_widget = MCPGardeFouWidget(self)
        self.garde_fou_widget.queue_updated.connect(self._on_queue_updated)
        self.stacked_widget.addWidget(self.garde_fou_widget)

        outer_layout.addWidget(self.stacked_widget, 1)

        self._refresh_snippet_view()

    def _on_sub_tab_changed(self, index: int) -> None:
        """Bascule entre la vue Supervision et la vue Garde-Fou."""
        self.stacked_widget.setCurrentIndex(index)
        if index == 1 and hasattr(self, "garde_fou_widget"):
            self.garde_fou_widget.reload_pending_patches()

    def _on_queue_updated(self, count: int) -> None:
        """Actualise dynamiquement l'intitulé et le badge du sous-onglet Garde-Fou."""
        text = tr("Garde-Fou & Validation (%1)", count) if count > 0 else self.tr("Garde-Fou & Validation")
        self.sub_tab_bar.setTabText(1, text)
        icon_color = DesignTokens.COLOR_RED if count > 0 else DesignTokens.TEXT_SECONDARY
        self.sub_tab_bar.setTabIcon(1, load_phosphor_icon("ph.shield-check", color=icon_color))

    def _on_mcp_patch_staged_event(self, event: MCPPatchStagedEvent) -> None:
        data = {
            "patch_id": event.patch_id,
            "patch_type": event.patch_type,
            "note_id": event.target_id,
            "title": event.title or str(event.details.get("title", "")),
        }
        self._patch_staged_received.emit(data)

    def on_patch_staged(self, data: dict[str, Any]) -> None:
        """Traite l'arrivée d'une proposition de patch staged par un agent MCP."""
        patch_id = str(data.get("patch_id", ""))
        is_duplicate = bool(patch_id and patch_id == self._last_notified_patch_id)
        self._last_notified_patch_id = patch_id

        if hasattr(self, "garde_fou_widget"):
            self.garde_fou_widget.reload_pending_patches()

        if not is_duplicate:
            note_id = data.get("note_id")
            title = data.get("title")
            if note_id:
                msg = tr("Nouvelle proposition de refactorisation reçue (#%1)", note_id)
            elif title:
                msg = tr("Nouvelle proposition reçue (%1)", title)
            else:
                msg = self.tr("Nouvelle proposition de refactorisation reçue")
            show_toast(self, msg, level="info")

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

        if hasattr(self, "sub_tab_bar"):
            text_sec = getattr(profile, "text_secondary", DesignTokens.TEXT_SECONDARY)
            bg_hov = getattr(profile, "bg_hover", DesignTokens.BG_HOVER)
            self.sub_tab_bar.setStyleSheet(f"""
                QTabBar#mcp_sub_tab_bar {{
                    background-color: transparent;
                    font-size: 12px;
                }}
                QTabBar#mcp_sub_tab_bar::tab {{
                    background-color: transparent;
                    color: {text_sec};
                    padding: 6px 14px;
                    border: none;
                    border-bottom: 2px solid transparent;
                    margin-right: 4px;
                    font-weight: 500;
                }}
                QTabBar#mcp_sub_tab_bar::tab:hover {{
                    color: {text_primary};
                    background-color: {bg_hov};
                    border-radius: 4px 4px 0 0;
                }}
                QTabBar#mcp_sub_tab_bar::tab:selected {{
                    color: {accent_primary};
                    border-bottom: 2px solid {accent_primary};
                    font-weight: 600;
                }}
            """)

        if hasattr(self, "garde_fou_widget") and hasattr(self.garde_fou_widget, "refresh_theme"):
            self.garde_fou_widget.refresh_theme(profile)

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
        if hasattr(self, "card_activity"):
            self.card_activity.setStyleSheet(card_style_tpl.format(name="mcp_card_activity", bg=bg_panel, border=border_color))
        if hasattr(self, "table_activity"):
            bg_act = getattr(profile, "bg_active", DesignTokens.BG_ACTIVE)
            text_sec = getattr(profile, "text_secondary", DesignTokens.TEXT_SECONDARY)
            self.table_activity.setStyleSheet(f"""
                QTableWidget#mcp_table_activity {{
                    background-color: {bg_main};
                    color: {text_primary};
                    border: 1px solid {border_color};
                    border-radius: 6px;
                    gridline-color: transparent;
                    selection-background-color: {bg_act};
                    selection-color: {text_primary};
                }}
                QTableWidget#mcp_table_activity::item {{
                    padding: 4px 8px;
                    border-bottom: 1px solid {border_color};
                }}
                QHeaderView::section {{
                    background-color: {bg_panel};
                    color: {text_sec};
                    font-size: 11px;
                    font-weight: 600;
                    padding: 6px 8px;
                    border: none;
                    border-bottom: 1px solid {border_color};
                }}
            """)

    def _create_status_badge_cell(self, status: str) -> QWidget:
        if status == "success":
            badge = StatusBadge(self.tr("Succès"), "ph.check-circle", variant="success")
        elif status == "error":
            badge = StatusBadge(self.tr("Erreur"), "ph.warning-circle", variant="danger")
        else:
            badge = StatusBadge(self.tr("En cours"), "ph.hourglass-simple", variant="warning")

        wrapper = QWidget()
        wrapper.setStyleSheet("background: transparent; border: none;")
        wrap_layout = QHBoxLayout(wrapper)
        wrap_layout.setContentsMargins(4, 2, 4, 2)
        wrap_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        wrap_layout.addWidget(badge)
        return wrapper

    def _create_activity_row(self, row: int, record_data: dict[str, Any]) -> None:
        call_id = str(record_data.get("call_id", ""))
        tool_name = str(record_data.get("tool_name", ""))
        started_at_str = str(record_data.get("started_at", ""))
        time_str = started_at_str[11:19] if len(started_at_str) >= 19 else started_at_str
        status = str(record_data.get("status", "running"))
        duration_ms = float(record_data.get("duration_ms", 0.0))
        args_summary = str(record_data.get("args_summary", ""))

        item_time = QTableWidgetItem(time_str)
        item_time.setData(Qt.ItemDataRole.UserRole, call_id)
        item_time.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table_activity.setItem(row, 0, item_time)

        item_tool = QTableWidgetItem(tool_name)
        font = QFont(DesignTokens.FONT_CODE)
        item_tool.setFont(font)
        self.table_activity.setItem(row, 1, item_tool)

        self.table_activity.setCellWidget(row, 2, self._create_status_badge_cell(status))

        dur_text = "—"
        if status != "running":
            dur_text = tr("%1 ms", duration_ms) if duration_ms < 1000 else tr("%1 s", round(duration_ms / 1000, 2))
        item_dur = QTableWidgetItem(dur_text)
        item_dur.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.table_activity.setItem(row, 3, item_dur)

        item_args = QTableWidgetItem(args_summary)
        item_args.setToolTip(args_summary)
        self.table_activity.setItem(row, 4, item_args)

    def _on_activity_row_clicked(self, row: int, column: int) -> None:
        item = self.table_activity.item(row, 0)
        if not item:
            return
        call_id = item.data(Qt.ItemDataRole.UserRole)
        if not call_id:
            return
        record = self._tracker.get_record(str(call_id))
        if record:
            dialog = MCPActivityDetailDialog(record, parent=self)
            dialog.exec()

    def clear_activity_history(self) -> None:
        self._tracker.clear_history()

    def _load_activity_history(self) -> None:
        self.table_activity.setRowCount(0)
        records = self._tracker.get_history()
        for rec in reversed(records):
            row = self.table_activity.rowCount()
            self.table_activity.insertRow(row)
            self._create_activity_row(row, rec.to_dict())
        self._update_activity_empty_state()

    def _on_activity_started(self, record_data: dict[str, Any]) -> None:
        self.table_activity.insertRow(0)
        self._create_activity_row(0, record_data)
        self._update_activity_empty_state()

    def _on_activity_updated(self, record_data: dict[str, Any]) -> None:
        call_id = str(record_data.get("call_id", ""))
        for row in range(self.table_activity.rowCount()):
            item = self.table_activity.item(row, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == call_id:
                status = str(record_data.get("status", "success"))
                duration_ms = float(record_data.get("duration_ms", 0.0))
                self.table_activity.setCellWidget(row, 2, self._create_status_badge_cell(status))
                dur_text = tr("%1 ms", duration_ms) if duration_ms < 1000 else tr("%1 s", round(duration_ms / 1000, 2))
                item_dur = self.table_activity.item(row, 3)
                if item_dur:
                    item_dur.setText(dur_text)
                else:
                    new_item_dur = QTableWidgetItem(dur_text)
                    new_item_dur.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    self.table_activity.setItem(row, 3, new_item_dur)
                break

    def _on_history_cleared(self) -> None:
        self.table_activity.setRowCount(0)
        self._update_activity_empty_state()

    def _update_activity_empty_state(self) -> None:
        count = self.table_activity.rowCount()
        if count == 0:
            self.badge_activity_count.setText(self.tr("0 appel"))
            self.lbl_empty_activity.setVisible(True)
            self.table_activity.setVisible(False)
            self.btn_clear_activity.setEnabled(False)
        else:
            text = tr("%1 appel", count) if count == 1 else tr("%1 appels", count)
            self.badge_activity_count.setText(text)
            self.lbl_empty_activity.setVisible(False)
            self.table_activity.setVisible(True)
            self.btn_clear_activity.setEnabled(True)

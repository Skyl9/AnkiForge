"""Tableau de bord autonome et interactif du serveur MCP local (Model Context Protocol).

Hébergé en tant qu'onglet de premier niveau dans la vue MCP & Agents.
Pilote la sous-navigation modulaire via SegmentedTabBar (mode subtab) entre
le cockpit de supervision opérationnelle (MCPSupervisionWidget) et l'espace
Garde-Fou & Validation (MCPGardeFouWidget).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QStackedWidget,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from ankiforge.services.ai.mcp_tracker import MCPActivityRecord
from ankiforge.ui.components.badges import Badge, StatusBadge
from ankiforge.ui.components.buttons import IconButton, PrimaryButton, SecondaryButton
from ankiforge.ui.components.tabs.segmented_tab_bar import SegmentedTabBar
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.views.consultant_view.widgets.mcp_garde_fou_widget import MCPGardeFouWidget
from ankiforge.ui.views.consultant_view.widgets.mcp_supervision_widget import MCPSupervisionWidget
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
    """Tableau de bord opérationnel du serveur MCP local avec SegmentedTabBar."""

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
        self._last_notified_patch_id: str | None = None

        if self._token is None:
            self._load_token_from_disk()

        self._setup_ui()
        self.set_status(initial_status, port=initial_port, token=self._token)

        self._patch_staged_received.connect(self.on_patch_staged)
        event_bus.subscribe(MCPPatchStagedEvent, self._on_mcp_patch_staged_event)

        # Initialisation dynamique de la file du Garde-Fou
        self.garde_fou_widget.reload_pending_patches()

    @property
    def current_status(self) -> str:
        return self.supervision_widget.current_status

    @property
    def port(self) -> int:
        return self.supervision_widget.port

    @property
    def host(self) -> str:
        return self.supervision_widget.host

    @property
    def token(self) -> str | None:
        return self.supervision_widget.token

    @property
    def url(self) -> str:
        return self.supervision_widget.url

    @property
    def sse_url(self) -> str:
        return self.supervision_widget.sse_url

    @property
    def pending_request(self) -> dict[str, Any] | None:
        return self.supervision_widget.pending_request

    # ── Propriétés de commodité et rétrocompatibilité ──
    @property
    def btn_start(self) -> PrimaryButton:
        return self.supervision_widget.btn_start

    @property
    def btn_stop(self) -> SecondaryButton:
        return self.supervision_widget.btn_stop

    @property
    def btn_restart(self) -> SecondaryButton:
        return self.supervision_widget.btn_restart

    @property
    def btn_rotate_token(self) -> SecondaryButton:
        return self.supervision_widget.btn_rotate_token

    @property
    def btn_open_prefs(self) -> SecondaryButton:
        return self.supervision_widget.btn_open_prefs

    @property
    def card_lifecycle(self) -> QFrame:
        return self.supervision_widget.card_lifecycle

    @property
    def card_endpoints(self) -> QFrame:
        return self.supervision_widget.card_endpoints

    @property
    def card_snippets(self) -> QFrame:
        return self.supervision_widget.card_snippets

    @property
    def banner_context_request(self) -> QFrame:
        return self.supervision_widget.banner_context_request

    @property
    def lbl_request_context(self) -> QLabel:
        return self.supervision_widget.lbl_request_context

    @property
    def btn_copy_request_prompt(self) -> PrimaryButton:
        return self.supervision_widget.btn_copy_request_prompt

    @property
    def btn_dismiss_request(self) -> IconButton:
        return self.supervision_widget.btn_dismiss_request

    @property
    def edit_request_prompt(self) -> QPlainTextEdit:
        return self.supervision_widget.edit_request_prompt

    @property
    def status_badge(self) -> Badge:
        return self.supervision_widget.status_badge

    @property
    def lbl_port_info(self) -> QLabel:
        return self.supervision_widget.lbl_port_info

    @property
    def lbl_transport_info(self) -> QLabel:
        return self.supervision_widget.lbl_transport_info

    @property
    def tab_bar_clients(self) -> QTabBar:
        return self.supervision_widget.tab_bar_clients

    @property
    def lbl_snippet_hint(self) -> QLabel:
        return self.supervision_widget.lbl_snippet_hint

    @property
    def edit_snippet_code(self) -> QPlainTextEdit:
        return self.supervision_widget.edit_snippet_code

    @property
    def btn_copy_snippet(self) -> PrimaryButton:
        return self.supervision_widget.btn_copy_snippet

    @property
    def btn_toggle_token(self) -> IconButton:
        return self.supervision_widget.btn_toggle_token

    @property
    def btn_copy_token(self) -> SecondaryButton:
        return self.supervision_widget.btn_copy_token

    @property
    def btn_copy_url_http(self) -> SecondaryButton:
        return self.supervision_widget.btn_copy_url_http

    @property
    def btn_copy_url_sse(self) -> SecondaryButton:
        return self.supervision_widget.btn_copy_url_sse

    @property
    def edit_url_http(self) -> QLineEdit:
        return self.supervision_widget.edit_url_http

    @property
    def edit_url_sse(self) -> QLineEdit:
        return self.supervision_widget.edit_url_sse

    @property
    def edit_token(self) -> QLineEdit:
        return self.supervision_widget.edit_token

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
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        # ── Barre de sous-onglets supérieure (SegmentedTabBar) ────────────
        tab_container = QWidget()
        tab_layout = QHBoxLayout(tab_container)
        tab_layout.setContentsMargins(16, 8, 16, 4)
        tab_layout.setSpacing(0)

        self.sub_tab_bar = SegmentedTabBar(mode="subtab", parent=self)
        self.sub_tab_bar.setObjectName("mcp_sub_tab_bar")
        self.sub_tab_bar.add_tab("supervision", self.tr("Supervision & Configuration"), icon_name="ph.sliders")
        self.sub_tab_bar.add_tab("garde_fou", self.tr("Garde-Fou & Validation"), icon_name="ph.shield-check")
        self.sub_tab_bar.tab_index_changed.connect(self._on_sub_tab_changed)

        tab_layout.addWidget(self.sub_tab_bar)
        tab_layout.addStretch()
        outer_layout.addWidget(tab_container)

        tab_separator = QFrame()
        tab_separator.setFixedHeight(1)
        tab_separator.setStyleSheet(f"background-color: {DesignTokens.BORDER_COLOR}; border: none;")
        outer_layout.addWidget(tab_separator)

        # ── Empilement des vues ───────────────────────────────────────────
        self.stacked_widget = QStackedWidget(self)

        # Sous-onglet 0 : Cockpit de supervision Zero-Scroll
        self.supervision_widget = MCPSupervisionWidget(
            initial_status=self._status,
            initial_port=self._port,
            initial_token=self._token,
            parent=self,
        )
        self.supervision_widget.start_requested.connect(self.start_requested.emit)
        self.supervision_widget.stop_requested.connect(self.stop_requested.emit)
        self.supervision_widget.restart_requested.connect(self.restart_requested.emit)
        self.supervision_widget.rotate_token_requested.connect(self.rotate_token_requested.emit)
        self.supervision_widget.open_preferences_requested.connect(self.open_preferences_requested.emit)
        self.stacked_widget.addWidget(self.supervision_widget)

        # Sous-onglet 1 : Espace Garde-Fou & Validation
        self.garde_fou_widget = MCPGardeFouWidget(self)
        self.garde_fou_widget.queue_updated.connect(self._on_queue_updated)
        self.stacked_widget.addWidget(self.garde_fou_widget)

        outer_layout.addWidget(self.stacked_widget, 1)

    def _on_sub_tab_changed(self, index: int) -> None:
        """Bascule entre la vue Supervision et la vue Garde-Fou."""
        self.stacked_widget.setCurrentIndex(index)
        if index == 1 and hasattr(self, "garde_fou_widget"):
            self.garde_fou_widget.reload_pending_patches()

    def _on_queue_updated(self, count: int) -> None:
        """Actualise dynamiquement l'intitulé et le badge du sous-onglet Garde-Fou."""
        text = tr("Garde-Fou & Validation (%1)", count) if count > 0 else self.tr("Garde-Fou & Validation")
        self.sub_tab_bar.set_tab_text("garde_fou", text)
        badge_val = str(count) if count > 0 else ""
        self.sub_tab_bar.set_tab_badge("garde_fou", badge_val)
        icon_color = DesignTokens.COLOR_RED if count > 0 else DesignTokens.TEXT_SECONDARY
        self.sub_tab_bar.set_tab_icon("garde_fou", load_phosphor_icon("ph.shield-check", color=icon_color))

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
        if hasattr(self, "supervision_widget"):
            self.supervision_widget.set_status(status, port=port, token=token, message=message)

    def toggle_token_visibility(self) -> None:
        self.supervision_widget.toggle_token_visibility()

    def copy_url(self) -> None:
        self.supervision_widget.copy_url()

    def copy_sse_url(self) -> None:
        self.supervision_widget.copy_sse_url()

    def copy_token(self) -> None:
        self.supervision_widget.copy_token()

    def get_snippet_config(self, client: str) -> str:
        return self.supervision_widget.get_snippet_config(client)

    def copy_current_snippet(self) -> None:
        self.supervision_widget.copy_current_snippet()

    def set_pending_request(self, context_item: Any, initial_prompt: str) -> None:
        self.supervision_widget.set_pending_request(context_item, initial_prompt)

    def refresh_theme(self, profile: Any) -> None:
        """Adapte les styles au profil de thème actif."""
        if hasattr(self, "sub_tab_bar") and hasattr(self.sub_tab_bar, "refresh_theme"):
            self.sub_tab_bar.refresh_theme(profile)
        if hasattr(self, "supervision_widget") and hasattr(self.supervision_widget, "refresh_theme"):
            self.supervision_widget.refresh_theme(profile)
        if hasattr(self, "garde_fou_widget") and hasattr(self.garde_fou_widget, "refresh_theme"):
            self.garde_fou_widget.refresh_theme(profile)


__all__ = ["MCPServerDashboardWidget", "MCPActivityDetailDialog"]

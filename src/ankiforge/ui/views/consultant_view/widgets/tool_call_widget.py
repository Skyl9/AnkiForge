from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from ankiforge.ui.components import Badge
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.views.consultant_view.constants import apply_pill_style
from ankiforge.utils.icon_loader import load_phosphor_icon


class ToolCallWidget(QFrame):
    """Affiche l'exécution en direct d'un outil MCP / Python avec payload et observation."""

    def __init__(
        self,
        tool_name: str,
        args_json: str = "{}",
        result_str: str = "",
        is_error: bool = False,
        is_running: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.tool_name = tool_name
        self.args_json = args_json
        self.result_str = result_str
        self.is_error = is_error
        self.is_running = is_running
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self._setup_style()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        header = QHBoxLayout()
        header.setSpacing(8)

        self.icon_lbl = QLabel()
        header.addWidget(self.icon_lbl)

        self.lbl_tool = QLabel(f"Outil invoqué : <b>{tool_name}</b>")
        self.lbl_tool.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11px;")
        header.addWidget(self.lbl_tool, 1)

        self.badge_status = Badge("Exécution...", variant="status")
        header.addWidget(self.badge_status)

        self.btn_toggle = QPushButton("Voir données ▾")
        self.btn_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle.setStyleSheet(f"QPushButton {{ background: transparent; border: none; color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; }}")
        self.btn_toggle.clicked.connect(self._toggle_details)
        header.addWidget(self.btn_toggle)

        layout.addLayout(header)

        self.details_box = QWidget()
        details_layout = QVBoxLayout(self.details_box)
        details_layout.setContentsMargins(0, 4, 0, 0)
        details_layout.setSpacing(4)

        self.lbl_args = QLabel(f"<b>Entrée (JSON) :</b> <code>{args_json}</code>")
        self.lbl_args.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-family: monospace;")
        self.lbl_args.setWordWrap(True)
        details_layout.addWidget(self.lbl_args)

        self.edit_result = QPlainTextEdit()
        self.edit_result.setReadOnly(True)
        self.edit_result.setPlainText(result_str)
        self.edit_result.setMaximumHeight(90)
        self.edit_result.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {DesignTokens.BG_MAIN};
                color: {DesignTokens.SYNTAX_TAG};
                font-family: '{DesignTokens.FONT_CODE}';
                font-size: 11px;
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 4px;
                padding: 6px;
            }}
        """)
        details_layout.addWidget(self.edit_result)

        self.details_box.hide()
        layout.addWidget(self.details_box)

        self._update_state()

    def _setup_style(self) -> None:
        if self.is_running:
            border_color = "rgba(234, 179, 8, 0.4)"
            bg_color = "rgba(234, 179, 8, 0.08)"
        elif self.is_error:
            border_color = "rgba(239, 68, 68, 0.4)"
            bg_color = "rgba(239, 68, 68, 0.08)"
        else:
            border_color = "rgba(16, 185, 129, 0.35)"
            bg_color = "rgba(16, 185, 129, 0.08)"

        self.setStyleSheet(f"""
            ToolCallWidget {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-radius: 8px;
            }}
            ToolCallWidget QLabel {{
                background: transparent;
            }}
        """)

    def _update_state(self) -> None:
        self._setup_style()
        if self.is_running:
            self.icon_lbl.setPixmap(load_phosphor_icon("ph.spinner", color=DesignTokens.COLOR_YELLOW).pixmap(14, 14))
            self.badge_status.setText("En cours...")
            apply_pill_style(self.badge_status, DesignTokens.COLOR_YELLOW)
        elif self.is_error:
            self.icon_lbl.setPixmap(load_phosphor_icon("ph.x-circle", color=DesignTokens.COLOR_RED).pixmap(14, 14))
            self.badge_status.setText("Échec")
            apply_pill_style(self.badge_status, DesignTokens.COLOR_RED)
        else:
            icon_name = "ph.database" if "peewee" in self.tool_name or "sql" in self.tool_name else ("ph.palette" if "css" in self.tool_name else "ph.check-circle")
            self.icon_lbl.setPixmap(load_phosphor_icon(icon_name, color=DesignTokens.COLOR_GREEN).pixmap(14, 14))
            self.badge_status.setText("Succès")
            apply_pill_style(self.badge_status, DesignTokens.COLOR_GREEN)

    def update_result(self, result_str: str, is_error: bool = False) -> None:
        """Met à jour le résultat de l'exécution de l'outil et passe de l'état En cours à Succès/Échec."""
        self.result_str = result_str
        self.is_error = is_error
        self.is_running = False
        self.edit_result.setPlainText(result_str)
        self._update_state()

    def _toggle_details(self) -> None:
        if self.details_box.isHidden():
            self.details_box.show()
            self.btn_toggle.setText("Masquer ▴")
        else:
            self.details_box.hide()
            self.btn_toggle.setText("Voir données ▾")

    def refresh_theme(self, profile: Any) -> None:
        self._setup_style()
        self.lbl_tool.setStyleSheet(f"color: {profile.text_primary}; font-size: 11px;")

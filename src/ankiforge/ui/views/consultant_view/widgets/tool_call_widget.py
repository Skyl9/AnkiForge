from typing import Any, Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from ankiforge.ui.components import Badge
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.views.consultant_view.constants import apply_pill_style
from ankiforge.utils.icon_loader import load_phosphor_icon


class ToolCallWidget(QFrame):
    """Affiche l'exécution d'un outil MCP / Python avec payload et observation."""

    def __init__(self, tool_name: str, args_json: str, result_str: str, is_error: bool = False, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.tool_name = tool_name
        self.is_error = is_error
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        border_color = "rgba(239, 68, 68, 0.4)" if is_error else "rgba(16, 185, 129, 0.35)"
        bg_color = "rgba(239, 68, 68, 0.08)" if is_error else "rgba(16, 185, 129, 0.08)"

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

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        header = QHBoxLayout()
        header.setSpacing(8)

        self.icon_lbl = QLabel()
        icon_name = "ph.database" if "peewee" in tool_name or "sql" in tool_name else ("ph.palette" if "css" in tool_name else "ph.wrench")
        icon_color = "#f87171" if is_error else "#34d399"
        self.icon_lbl.setPixmap(load_phosphor_icon(icon_name, color=icon_color).pixmap(14, 14))
        header.addWidget(self.icon_lbl)

        self.lbl_tool = QLabel(f"Outil invoqué : <b>{tool_name}</b>")
        self.lbl_tool.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11px;")
        header.addWidget(self.lbl_tool, 1)

        badge_status = Badge("Échec" if is_error else "Succès", variant="status")
        apply_pill_style(badge_status, "#ef4444" if is_error else "#10b981")
        header.addWidget(badge_status)

        self.btn_toggle = QPushButton("Voir données ▾")
        self.btn_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle.setStyleSheet("QPushButton { background: transparent; border: none; color: #94a3b8; font-size: 10px; font-weight: bold; }")
        self.btn_toggle.clicked.connect(self._toggle_details)
        header.addWidget(self.btn_toggle)

        layout.addLayout(header)

        self.details_box = QWidget()
        details_layout = QVBoxLayout(self.details_box)
        details_layout.setContentsMargins(0, 4, 0, 0)
        details_layout.setSpacing(4)

        lbl_args = QLabel(f"<b>Entrée (JSON) :</b> <code>{args_json}</code>")
        lbl_args.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-family: monospace;")
        lbl_args.setWordWrap(True)
        details_layout.addWidget(lbl_args)

        edit_result = QPlainTextEdit()
        edit_result.setReadOnly(True)
        edit_result.setPlainText(result_str)
        edit_result.setMaximumHeight(90)
        edit_result.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {DesignTokens.BG_MAIN};
                color: #38bdf8;
                font-family: '{DesignTokens.FONT_CODE}';
                font-size: 11px;
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 4px;
                padding: 6px;
            }}
        """)
        details_layout.addWidget(edit_result)

        self.details_box.hide()
        layout.addWidget(self.details_box)

    def _toggle_details(self) -> None:
        if self.details_box.isHidden():
            self.details_box.show()
            self.btn_toggle.setText("Masquer ▴")
        else:
            self.details_box.hide()
            self.btn_toggle.setText("Voir données ▾")

    def refresh_theme(self, profile: Any) -> None:
        border_color = "rgba(239, 68, 68, 0.4)" if self.is_error else "rgba(16, 185, 129, 0.35)"
        bg_color = "rgba(239, 68, 68, 0.08)" if self.is_error else "rgba(16, 185, 129, 0.08)"
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
        self.lbl_tool.setStyleSheet(f"color: {profile.text_primary}; font-size: 11px;")

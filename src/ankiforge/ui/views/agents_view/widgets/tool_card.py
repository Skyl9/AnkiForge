from typing import Any, Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ankiforge.ui.components import Badge
from ankiforge.ui.theme import DesignTokens


class ToolPermissionCard(QFrame):
    """Carte interactive pour cocher/décocher une permission d'outil."""

    def __init__(
        self,
        tool_key: str = "",
        label: str = "",
        description: str = "",
        category: str = "Natif",
        category_color: str = "#3b82f6",
        is_checked: bool = False,
        parent: Optional[QWidget] = None,
        tool_name: str = "",
        display_name: str = "",
    ) -> None:
        super().__init__(parent)
        self.tool_key = tool_key or tool_name
        self.tool_name = self.tool_key
        display_title = label or display_name or self.tool_key
        self.setObjectName("toolPermCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f"""
            QFrame#toolPermCard {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
            QFrame#toolPermCard:hover {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
                background-color: {DesignTokens.BG_HOVER};
            }}
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)

        self.checkbox = QCheckBox()
        self.checkbox.setChecked(is_checked)
        self.checkbox.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(self.checkbox)

        col = QVBoxLayout()
        col.setSpacing(2)
        lbl_title = QLabel(display_title)
        lbl_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: bold; font-size: 12px; background: transparent;")
        col.addWidget(lbl_title)

        lbl_desc = QLabel(description)
        lbl_desc.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; background: transparent;")
        lbl_desc.setWordWrap(True)
        col.addWidget(lbl_desc)
        layout.addLayout(col, 1)

        badge_variant = "primary" if category == "MCP" else ("info" if category == "Natif" else "warning")
        self.badge = Badge(category, variant=badge_variant)
        self.badge.setFixedHeight(20)
        layout.addWidget(self.badge)

    def mousePressEvent(self, event: Any) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.checkbox.setChecked(not self.checkbox.isChecked())
        super().mousePressEvent(event)

    def isChecked(self) -> bool:
        return self.checkbox.isChecked()

    def setChecked(self, checked: bool) -> None:
        self.checkbox.setChecked(checked)

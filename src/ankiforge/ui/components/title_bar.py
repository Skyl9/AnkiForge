"""
Barre de titre globale AnkiForge.
Barre 28px pour le drag macOS avec titre centré.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QWidget,
)

from ankiforge.ui.theme import DesignTokens


class GlobalTitleBar(QFrame):
    """Barre de titre globale 28px pour macOS drag."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("GlobalTitleBar")
        self.setFixedHeight(DesignTokens.GLOBAL_TOPBAR_HEIGHT)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.title_lbl = QLabel("AnkiForge")
        self.title_lbl.setObjectName("GlobalTitleBarLabel")
        self.title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title_lbl)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.window().windowHandle().startSystemMove()
        super().mousePressEvent(event)

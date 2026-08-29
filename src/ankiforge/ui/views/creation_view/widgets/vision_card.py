from typing import Any
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame


class VisionCard(QFrame):
    """Carte interactive cliquable pour l'activation du mode Vision."""

    clicked = Signal()

    def mousePressEvent(self, event: Any) -> None:
        super().mousePressEvent(event)
        self.clicked.emit()

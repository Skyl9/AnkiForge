"""
Vue et Composant SmartMergeView pour la résolution visuelle des conflits.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QVBoxLayout,
    QWidget,
)

from ankiforge.services.cards.import_manager import ConflictItem
from ankiforge.ui.dialogs.smart_merge_dialog import SmartMergeDialog


class MergeView(QWidget):
    """
    Vue conteneur pour intégrer le dialogue ou widget Smart Merge dans l'IDE.
    """

    merge_resolved = Signal(dict)

    def __init__(self, conflicts: list[ConflictItem] | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.conflicts = conflicts or []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        if self.conflicts:
            self.dialog = SmartMergeDialog(self.conflicts, self)
            self.dialog.merge_completed.connect(self.merge_resolved.emit)
            layout.addWidget(self.dialog)


# Alias pour la rétrocompatibilité
SmartMergeView = MergeView

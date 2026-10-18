"""Vue et Composant SmartMergeView pour la résolution visuelle des conflits."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QVBoxLayout,
    QWidget,
)

from ankiforge.services.cards.import_manager import ConflictItem
from ankiforge.ui.dialogs.smart_merge_dialog import SmartMergeDialog

if TYPE_CHECKING:
    from ankiforge.ui.shortcuts import ShortcutManager


class MergeView(QWidget):
    """Vue conteneur pour intégrer le dialogue ou widget Smart Merge dans l'IDE."""

    merge_resolved = Signal(dict)

    def __init__(
        self,
        conflicts: list[ConflictItem] | None = None,
        parent: QWidget | None = None,
        shortcut_manager: ShortcutManager | None = None,
    ) -> None:
        super().__init__(parent)
        self.conflicts = conflicts or []
        self._shortcut_manager = shortcut_manager
        self.dialog: SmartMergeDialog | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        if self.conflicts:
            self.dialog = SmartMergeDialog(self.conflicts, self, shortcut_manager=self._shortcut_manager)
            self.dialog.merge_completed.connect(self.merge_resolved.emit)
            layout.addWidget(self.dialog)

    @property
    def shortcut_manager(self) -> ShortcutManager | None:
        """Manager des raccourcis clavier."""
        return self._shortcut_manager

    def set_shortcut_manager(self, manager: ShortcutManager) -> None:
        """Injecte le ShortcutManager central et le transmet au dialogue."""
        self._shortcut_manager = manager
        if self.dialog is not None:
            self.dialog.set_shortcut_manager(manager)

    def run_primary_action(self) -> None:
        """Valide la fusion (routeur Ctrl+Entrée)."""
        if self.dialog is not None:
            self.dialog._on_confirm_merge()


# Alias pour la rétrocompatibilité
SmartMergeView = MergeView

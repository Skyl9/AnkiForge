"""
Module de compatibilité ascendante pour VersionHistoryDialog.
Redirige directement vers TimeMachineDialog.
"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from ankiforge.database.models import NoteModel
from ankiforge.ui.widgets.time_machine_dialog import TimeMachineDialog


class VersionHistoryDialog(TimeMachineDialog):
    """Alias pour TimeMachineDialog."""

    def __init__(self, note: NoteModel, parent: QWidget | None = None) -> None:
        super().__init__(note=note, parent=parent)

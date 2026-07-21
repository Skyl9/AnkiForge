"""
Compatibilité composant pour widgets réintégrés.
"""

from PySide6.QtWidgets import QLabel, QWidget
from .buttons import PrimaryButton, SecondaryButton, DangerButton, IconButton
from .panels import IdePanel, GlassPanel
from .inputs import StyledComboBox, DBComboBox

ActionButton = SecondaryButton
RoundedPanel = GlassPanel
HeaderLabel = QLabel
EmptyStateWidget = QWidget

__all__ = [
    "PrimaryButton",
    "SecondaryButton",
    "DangerButton",
    "IconButton",
    "ActionButton",
    "RoundedPanel",
    "HeaderLabel",
    "EmptyStateWidget",
    "IdePanel",
    "GlassPanel",
    "StyledComboBox",
    "DBComboBox",
]

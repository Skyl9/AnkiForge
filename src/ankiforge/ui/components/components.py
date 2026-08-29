"""
Compatibilité composant pour widgets réintégrés.
"""

from PySide6.QtWidgets import QLabel

from .buttons import ActionButton, DangerButton, IconButton, PrimaryButton, SecondaryButton
from .inputs import DBComboBox, StyledComboBox
from .panels import EmptyStateWidget, GlassPanel, IdePanel

RoundedPanel = GlassPanel
HeaderLabel = QLabel


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

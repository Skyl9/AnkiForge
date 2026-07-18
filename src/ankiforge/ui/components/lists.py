from PySide6.QtWidgets import QWidget, QLabel, QHBoxLayout, QVBoxLayout
from PySide6.QtCore import Signal, Qt
from ..theme import DesignTokens


class StyledListItem(QWidget):
    """Item de liste générique avec hover/active."""

    clicked = Signal()

    def mousePressEvent(self, event):
        self.clicked.emit()
        super().mousePressEvent(event)


class ActivityItem(QWidget):
    """Item d'activité : icône + texte principal + texte secondaire + timestamp."""

    def __init__(self, icon_name: str, title: str, subtitle: str, timestamp: str, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        self.icon_lbl = QLabel(icon_name)
        self.icon_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY};")

        vbox = QVBoxLayout()
        vbox.setSpacing(2)
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: bold;")
        subtitle_lbl = QLabel(subtitle)
        subtitle_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")
        vbox.addWidget(title_lbl)
        vbox.addWidget(subtitle_lbl)

        time_lbl = QLabel(timestamp)
        time_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")
        time_lbl.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)

        layout.addWidget(self.icon_lbl)
        layout.addLayout(vbox)
        layout.addStretch()
        layout.addWidget(time_lbl)


class DocTreeItem(QWidget):
    """Item d'arbre de fichiers avec icône, caret expand, nom."""

    pass


class ContextItem(QWidget):
    """Item de contexte AI avec badge type + nom + bouton supprimer."""

    removed = Signal()

    def __init__(self, type_name: str, name: str, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        self.setStyleSheet(f"background-color: {DesignTokens.BG_INPUT}; border-radius: {DesignTokens.RADIUS_SM}px;")

        type_lbl = QLabel(type_name)
        type_lbl.setStyleSheet(f"color: {DesignTokens.ACCENT_PRIMARY}; font-size: 10px; font-weight: bold;")

        name_lbl = QLabel(name)
        name_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY};")

        from .buttons import IconButton

        del_btn = IconButton("✕", size=16)
        del_btn.clicked.connect(self.removed.emit)

        layout.addWidget(type_lbl)
        layout.addWidget(name_lbl)
        layout.addStretch()
        layout.addWidget(del_btn)

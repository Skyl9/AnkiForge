from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PySide6.QtCore import Signal, Qt
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.components.buttons import IconButton
from ankiforge.utils.icon_loader import load_phosphor_icon


class StyledListItem(QWidget):
    """Item de liste générique avec hover/active."""

    clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            StyledListItem {{
                background-color: transparent;
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
            StyledListItem:hover {{
                background-color: {DesignTokens.BG_HOVER};
            }}
        """)

    def mouseReleaseEvent(self, event) -> None:
        from PySide6.QtGui import QMouseEvent

        if isinstance(event, QMouseEvent) and event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class ActivityItem(QWidget):
    """Item d'activité : icône + texte principal + texte secondaire + timestamp."""

    def __init__(self, icon_name: str, title: str, subtitle: str, timestamp: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)

        self.icon_lbl = QLabel()
        pixmap = load_phosphor_icon(icon_name, color=DesignTokens.TEXT_SECONDARY).pixmap(16, 16)
        self.icon_lbl.setPixmap(pixmap)
        layout.addWidget(self.icon_lbl)

        vbox = QVBoxLayout()
        self.title_lbl = QLabel(title)
        self.title_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: bold;")
        self.sub_lbl = QLabel(subtitle)
        self.sub_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")
        vbox.addWidget(self.title_lbl)
        vbox.addWidget(self.sub_lbl)
        layout.addLayout(vbox)

        layout.addStretch()

        self.time_lbl = QLabel(timestamp)
        self.time_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")
        layout.addWidget(self.time_lbl)


class DocTreeItem(QWidget):
    """Item d'arbre de fichiers avec icône, caret expand, nom."""

    def __init__(self, text: str, is_dir: bool = False, expanded: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(28)
        self.setStyleSheet(f"""
            DocTreeItem {{
                background-color: transparent;
                border-radius: {DesignTokens.RADIUS_SM - 2}px;
            }}
            DocTreeItem:hover {{
                background-color: {DesignTokens.BG_HOVER};
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(6)

        self.caret = QLabel("▼" if expanded else "▶")
        self.caret.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px;")
        if not is_dir:
            self.caret.setVisible(False)
        layout.addWidget(self.caret)

        icon = "📁" if is_dir else "📄"
        self.icon_lbl = QLabel(icon)
        layout.addWidget(self.icon_lbl)

        self.text_lbl = QLabel(text)
        self.text_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY};")
        layout.addWidget(self.text_lbl)
        layout.addStretch()


class ContextItem(QWidget):
    """Item de contexte AI avec badge type + nom + bouton supprimer."""

    removed = Signal()

    def __init__(self, type_badge: str, name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(32)
        self.setStyleSheet(f"""
            ContextItem {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 4, 0)

        self.badge = QLabel(type_badge)
        self.badge.setStyleSheet(f"""
            background-color: {DesignTokens.BG_PANEL};
            color: {DesignTokens.ACCENT_PRIMARY};
            border-radius: 4px;
            padding: 2px 4px;
            font-size: 10px;
            font-weight: bold;
        """)
        layout.addWidget(self.badge)

        self.name_lbl = QLabel(name)
        self.name_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY};")
        layout.addWidget(self.name_lbl)

        layout.addStretch()

        self.del_btn = IconButton("✕", "Remove", 24)
        self.del_btn.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; border: none; background: transparent;")
        self.del_btn.clicked.connect(self.removed.emit)
        layout.addWidget(self.del_btn)

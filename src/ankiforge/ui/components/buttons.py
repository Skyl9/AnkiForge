from PySide6.QtWidgets import QPushButton, QFrame, QLabel, QVBoxLayout, QWidget
from PySide6.QtCore import Signal, Qt
from ..theme import DesignTokens, apply_shadow


class PrimaryButton(QPushButton):
    """Bouton principal indigo avec glow. Usage: actions primaires."""

    def __init__(self, text: str, parent: QWidget | None = None):
        super().__init__(text, parent)
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {DesignTokens.ACCENT_PRIMARY};
                color: {DesignTokens.TEXT_PRIMARY};
                border: none;
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 8px 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {DesignTokens.ACCENT_HOVER};
            }}
        """)
        apply_shadow(self, blur=10, offset_y=0, color="rgba(99,102,241,0.4)")


class SecondaryButton(QPushButton):
    """Bouton secondaire avec bordure. Usage: actions secondaires."""

    def __init__(self, text: str, parent: QWidget | None = None):
        super().__init__(text, parent)
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {DesignTokens.BG_PANEL};
                color: {DesignTokens.TEXT_PRIMARY};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 8px 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {DesignTokens.BG_HOVER};
            }}
        """)


class DangerButton(QPushButton):
    """Bouton danger rouge. Variantes: filled et ghost."""

    def __init__(self, text: str, ghost: bool = False, parent: QWidget | None = None):
        super().__init__(text, parent)
        if ghost:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    color: {DesignTokens.COLOR_RED};
                    border: 1px solid {DesignTokens.COLOR_RED};
                    border-radius: {DesignTokens.RADIUS_SM}px;
                    padding: 8px 16px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background-color: rgba(239, 68, 68, 0.1);
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: {DesignTokens.COLOR_RED};
                    color: {DesignTokens.TEXT_PRIMARY};
                    border: none;
                    border-radius: {DesignTokens.RADIUS_SM}px;
                    padding: 8px 16px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background-color: #dc2626;
                }}
            """)


class IconButton(QPushButton):
    """Bouton icône 32x32 transparent. Usage: toolbars."""

    def __init__(self, icon_name: str, tooltip: str = "", size: int = 32, parent: QWidget | None = None):
        super().__init__(parent)
        self.setText(icon_name)
        self.setToolTip(tooltip)
        self.setFixedSize(size, size)
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {DesignTokens.TEXT_PRIMARY};
                border: none;
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
            QPushButton:hover {{
                background-color: {DesignTokens.BG_HOVER};
            }}
        """)


class PremiumActionCard(QFrame):
    """Grande carte d'action avec icône + titre + description. Usage: Dashboard."""

    clicked = Signal()

    def __init__(self, icon_name: str, title: str, description: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("PremiumActionCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            #PremiumActionCard {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
            #PremiumActionCard:hover {{
                border: 1px solid {DesignTokens.ACCENT_PRIMARY};
                background-color: {DesignTokens.BG_HOVER};
            }}
        """)
        apply_shadow(self, blur=12, offset_y=4, color="rgba(0,0,0,0.2)")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(8)

        self.icon_lbl = QLabel(icon_name)
        self.icon_lbl.setStyleSheet(f"color: {DesignTokens.ACCENT_PRIMARY}; font-size: 24px; border: none;")

        self.title_lbl = QLabel(title)
        self.title_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: bold; font-size: 14px; border: none;")

        self.desc_lbl = QLabel(description)
        self.desc_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; border: none;")
        self.desc_lbl.setWordWrap(True)

        layout.addWidget(self.icon_lbl)
        layout.addWidget(self.title_lbl)
        layout.addWidget(self.desc_lbl)
        layout.addStretch()

    def mousePressEvent(self, event):
        self.clicked.emit()
        super().mousePressEvent(event)

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon


class CollapsibleSection(QFrame):
    """Section d'onglet repliable : en-tête cliquable (titre + caret) et contenu masquable.

    Utilisée pour masquer les réglages avancés dans le modal de paramètres afin
    d'alléger l'interface et de n'exposer que l'essentiel par défaut.
    """

    def __init__(self, title: str, parent: QWidget | None = None, collapsed: bool = True) -> None:
        super().__init__(parent)
        self.setObjectName("CollapsibleSection")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._collapsed = collapsed
        self._apply_style()

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 6, 12, 8)
        root.setSpacing(6)

        self.btn_header = QPushButton()
        self.btn_header.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_header.setStyleSheet("background: transparent; border: none; text-align: left; padding: 2px 0;")
        header_layout = QHBoxLayout(self.btn_header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(6)

        self.lbl_title = QLabel(title)
        self.lbl_title.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px; font-weight: 600; background: transparent; border: none;")
        header_layout.addWidget(self.lbl_title)
        header_layout.addStretch()

        self.lbl_caret = QLabel()
        self.lbl_caret.setStyleSheet("background: transparent; border: none;")
        header_layout.addWidget(self.lbl_caret)

        root.addWidget(self.btn_header)

        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(10)
        root.addWidget(self.content)

        self.btn_header.clicked.connect(self.toggle)
        self.content.setVisible(not self._collapsed)
        self._update_caret()

    def _apply_style(self) -> None:
        self.setStyleSheet(f"""
            QFrame#CollapsibleSection {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)

    def _update_caret(self) -> None:
        icon = "ph.caret-right" if self._collapsed else "ph.caret-down"
        self.lbl_caret.setPixmap(load_phosphor_icon(icon, color=DesignTokens.TEXT_MUTED).pixmap(12, 12))

    def add_widget(self, widget: QWidget) -> None:
        self.content_layout.addWidget(widget)

    def add_layout(self, layout: QLayout) -> None:
        self.content_layout.addLayout(layout)

    def is_collapsed(self) -> bool:
        return self._collapsed

    def set_collapsed(self, collapsed: bool) -> None:
        if collapsed == self._collapsed:
            return
        self._collapsed = collapsed
        self.content.setVisible(not collapsed)
        self._update_caret()

    def toggle(self) -> None:
        self.set_collapsed(not self._collapsed)

    def refresh_theme(self, profile: Any) -> None:
        self.setStyleSheet(f"""
            QFrame#CollapsibleSection {{
                background-color: {profile.bg_panel};
                border: 1px solid {profile.border_color};
                border-radius: {profile.radius_md}px;
            }}
        """)
        self.lbl_title.setStyleSheet(f"color: {profile.text_secondary}; font-size: 11px; font-weight: 600; background: transparent; border: none;")
        icon = "ph.caret-right" if self._collapsed else "ph.caret-down"
        self.lbl_caret.setPixmap(load_phosphor_icon(icon, color=profile.text_muted).pixmap(12, 12))

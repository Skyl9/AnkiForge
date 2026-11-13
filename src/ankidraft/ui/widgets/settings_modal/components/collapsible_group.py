from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ankidraft.ui.theme import DesignTokens
from ankidraft.ui.widgets.settings_modal.components.settings_card import apply_pill_badge_style
from ankidraft.utils.icon_loader import load_phosphor_icon


class CollapsibleSettingsGroup(QFrame):
    """Groupe de réglages repliable (divulgation progressive).

    En-tête cliquable portant un titre configurable, un chevron Phosphor
    pivotant (``ph.caret-right`` / ``ph.caret-down``) et une pastille pill
    indiquant le nombre de contrôles masqués. Le contenu est replié par
    défaut afin de n'exposer que l'essentiel de l'onglet de paramètres.
    """

    toggled = Signal(bool)

    def __init__(
        self,
        title: str,
        parent: QWidget | None = None,
        expanded: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("CollapsibleSettingsGroup")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._expanded = expanded
        self._hidden_count = 0
        self._apply_style()

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 6, 12, 8)
        root.setSpacing(6)

        self.btn_header = QPushButton()
        self.btn_header.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_header.setStyleSheet("background: transparent; border: none; text-align: left; padding: 2px 0;")
        header_layout = QHBoxLayout(self.btn_header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)

        self.lbl_title = QLabel(title)
        self.lbl_title.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px; font-weight: 600; background: transparent; border: none;")
        header_layout.addWidget(self.lbl_title)
        header_layout.addStretch()

        self.lbl_badge = QLabel("0")
        self.lbl_badge.setStyleSheet("background: transparent; border: none;")
        apply_pill_badge_style(self.lbl_badge, DesignTokens.ACCENT_PRIMARY)
        self.lbl_badge.setVisible(self._hidden_count > 0)
        header_layout.addWidget(self.lbl_badge)

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
        self.content.setVisible(self._expanded)
        self._update_caret()
        self._update_badge()

    def _apply_style(self) -> None:
        self.setStyleSheet(
            f"""
            QFrame#CollapsibleSettingsGroup {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """
        )

    def _update_caret(self) -> None:
        icon = "ph.caret-right" if not self._expanded else "ph.caret-down"
        self.lbl_caret.setPixmap(load_phosphor_icon(icon, color=DesignTokens.TEXT_MUTED).pixmap(12, 12))

    def _update_badge(self) -> None:
        self.lbl_badge.setText(str(self._hidden_count))
        self.lbl_badge.setVisible(self._hidden_count > 0)

    def add_widget(self, widget: QWidget) -> None:
        self.content_layout.addWidget(widget)
        self._hidden_count += 1
        self._update_badge()

    def add_layout(self, layout: QLayout) -> None:
        self.content_layout.addLayout(layout)
        self._hidden_count += 1
        self._update_badge()

    def is_expanded(self) -> bool:
        """True si le contenu du groupe est actuellement déplié."""
        return self._expanded

    def set_expanded(self, expanded: bool) -> None:
        """Définit l'état déplié/replié et émet le signal ``toggled``."""
        if expanded == self._expanded:
            return
        self._expanded = expanded
        self.content.setVisible(expanded)
        self._update_caret()
        self.toggled.emit(expanded)

    def set_badge_count(self, count: int) -> None:
        """Définit manuellement le nombre affiché sur la pastille pill."""
        self._hidden_count = count
        self._update_badge()

    def toggle(self) -> None:
        self.set_expanded(not self._expanded)

    def refresh_theme(self, profile: Any) -> None:
        self.setStyleSheet(
            f"""
            QFrame#CollapsibleSettingsGroup {{
                background-color: {profile.bg_panel};
                border: 1px solid {profile.border_color};
                border-radius: {profile.radius_md}px;
            }}
        """
        )
        self.lbl_title.setStyleSheet(f"color: {profile.text_secondary}; font-size: 11px; font-weight: 600; background: transparent; border: none;")
        icon = "ph.caret-right" if not self._expanded else "ph.caret-down"
        self.lbl_caret.setPixmap(load_phosphor_icon(icon, color=profile.text_muted).pixmap(12, 12))
        apply_pill_badge_style(self.lbl_badge, profile.accent_primary)
        self.lbl_badge.setVisible(self._hidden_count > 0)

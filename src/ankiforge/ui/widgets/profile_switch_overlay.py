"""Overlay de feedback immédiat lors d'un basculement de profil.

Affiche un rideau semi-transparent avec un spinner et un message traduit afin
d'éviter le gel visuel (roue multicolore / beachball) pendant les opérations
I/O du changement de profil.
"""

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.theme_transition_overlay import SpinningIconLabel
from ankiforge.utils.i18n import tr


class ProfileSwitchOverlay(QWidget):
    """Overlay centré et semi-transparent affiché pendant le changement de profil."""

    def __init__(
        self,
        parent: QWidget,
        profile_name: str = "",
    ) -> None:
        super().__init__(parent)
        self._parent_widget = parent

        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setGeometry(parent.rect())

        if parent:
            parent.installEventFilter(self)

        self._setup_ui(profile_name)

        self.show()
        self.raise_()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched == self._parent_widget and event.type() == QEvent.Type.Resize:
            self.setGeometry(self._parent_widget.rect())
        return super().eventFilter(watched, event)

    def _setup_ui(self, profile_name: str) -> None:
        # Opacity effect sur l'overlay global
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity_effect)
        self._opacity_effect.setOpacity(0.95)

        # Fond assombri
        self.setStyleSheet(f"background-color: {DesignTokens._with_alpha(DesignTokens.BG_MAIN, 0.80)};")

        main_layout = QVBoxLayout(self)
        main_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Carte centrale
        self.card = QFrame()
        self.card.setFixedSize(380, 150)
        self.card.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(24, 20, 24, 20)
        card_layout.setSpacing(12)

        # Ligne d'en-tête avec icône rotative
        header_row = QHBoxLayout()
        header_row.setSpacing(14)

        self.spinner = SpinningIconLabel(icon_name="ph.spinner", color=DesignTokens.ACCENT_PRIMARY, size=32)
        header_row.addWidget(self.spinner)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)

        lbl_title = QLabel(tr("Changement de profil en cours..."))
        lbl_title.setFont(QFont(DesignTokens.FONT_MAIN, 12, QFont.Weight.Bold))
        lbl_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border: none; background: transparent;")

        lbl_sub = QLabel(tr("Basculement vers l'espace « %1 »...", profile_name) if profile_name else "")
        lbl_sub.setFont(QFont(DesignTokens.FONT_MAIN, 10))
        lbl_sub.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; border: none; background: transparent;")
        if not profile_name:
            lbl_sub.hide()

        text_col.addWidget(lbl_title)
        text_col.addWidget(lbl_sub)
        header_row.addLayout(text_col, 1)

        card_layout.addLayout(header_row)

        main_layout.addWidget(self.card)

    def close_overlay(self) -> None:
        """Arrête le spinner et supprime l'overlay de l'arbre des widgets."""
        if hasattr(self, "spinner") and self.spinner:
            self.spinner.stop()
        if self._parent_widget:
            self._parent_widget.removeEventFilter(self)
        self.deleteLater()

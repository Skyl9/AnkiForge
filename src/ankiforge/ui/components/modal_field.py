"""
Champ sélectionnable compact ouvrant une modale (mini DocumentPickerButton).

Affiche une icône + un libellé + un chevron ; le clic émet `clicked` et la vue
ouvre la fenêtre de sélection correspondante (DeckSelectWindow, ModelSelectWindow,
PersonaSelectWindow, PipelineSelectWindow, ModelDiscoveryDialog...).
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCursor, QMouseEvent
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon


class ModalField(QFrame):
    """
    Bouton-champ cliquable : icône + libellé principal (placeholder quand vide)
    + sous-titre optionnel + chevron. Le payload sélectionné est conservé.
    """

    clicked = Signal()
    value_changed = Signal(object)  # payload sélectionné (objet modèle ou None)

    def __init__(self, placeholder: str = "Sélectionner...", parent: QFrame | None = None) -> None:
        super().__init__(parent)
        self._placeholder = placeholder
        self._payload: Any = None
        self._label: str | None = None
        self._subtitle: str | None = None
        self._icon_name: str | None = None
        self._icon_color: str = DesignTokens.TEXT_MUTED

        self.setObjectName("ModalField")
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setMinimumHeight(34)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(8)

        self.icon_label = QLabel()
        self.icon_label.setFixedSize(18, 18)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setStyleSheet("background: transparent; border: none;")
        layout.addWidget(self.icon_label)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(0)
        self.title_label = QLabel()
        text_layout.addWidget(self.title_label)
        self.subtitle_label = QLabel()
        text_layout.addWidget(self.subtitle_label)
        layout.addLayout(text_layout, 1)

        self.chevron_label = QLabel()
        self.chevron_label.setPixmap(load_phosphor_icon("ph.caret-right", color=DesignTokens.TEXT_MUTED).pixmap(14, 14))
        self.chevron_label.setStyleSheet("background: transparent; border: none;")
        layout.addWidget(self.chevron_label)

        self.setStyleSheet(f"""
            QFrame#ModalField {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
            QFrame#ModalField:hover {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
                background-color: {DesignTokens.BG_HOVER};
            }}
        """)

        self._refresh_display()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def set_value(
        self,
        label: str,
        payload: Any = None,
        subtitle: str | None = None,
        icon_name: str | None = None,
        icon_color: str = DesignTokens.TEXT_MUTED,
        emit_signal: bool = True,
    ) -> None:
        """Définit la sélection affichée et son payload (objet modèle)."""
        same = self._values_equal(payload)
        self._label = label
        self._payload = payload
        self._subtitle = subtitle
        self._icon_name = icon_name
        self._icon_color = icon_color
        self._refresh_display()
        if emit_signal and not same:
            self.value_changed.emit(payload)

    def get_value(self) -> Any:
        """Retourne le payload sélectionné (None si vide)."""
        return self._payload

    def clear(self) -> None:
        """Réinitialise le champ (placeholder, payload à None)."""
        if self._payload is None and self._label is None:
            return
        self._label = None
        self._payload = None
        self._subtitle = None
        self._icon_name = None
        self._icon_color = DesignTokens.TEXT_MUTED
        self._refresh_display()
        self.value_changed.emit(None)

    def _values_equal(self, candidate: Any) -> bool:
        if candidate is self._payload:
            return True
        if candidate is None or self._payload is None:
            return False
        cand_id = getattr(candidate, "id", None)
        curr_id = getattr(self._payload, "id", None)
        if cand_id is not None and curr_id is not None:
            return cand_id == curr_id
        return bool(self._label == candidate)

    def _refresh_display(self) -> None:
        if self._label:
            self.title_label.setText(self._label)
            self.title_label.setStyleSheet(f"font-size: 12px; font-weight: 600; color: {DesignTokens.TEXT_PRIMARY}; background: transparent; border: none;")
            self.subtitle_label.setText(self._subtitle or "")
            self.subtitle_label.setVisible(bool(self._subtitle))
            self.subtitle_label.setStyleSheet(f"font-size: 10px; color: {DesignTokens.TEXT_MUTED}; background: transparent; border: none;")
            icon_name = self._icon_name or "ph.squares-four"
            icon_color = self._icon_color or DesignTokens.TEXT_MUTED
            self.icon_label.setPixmap(load_phosphor_icon(icon_name, color=icon_color).pixmap(16, 16))
        else:
            self.title_label.setText(self._placeholder)
            self.title_label.setStyleSheet(f"font-size: 12px; font-weight: 500; color: {DesignTokens.TEXT_MUTED}; background: transparent; border: none;")
            self.subtitle_label.setVisible(False)
            self.icon_label.setPixmap(load_phosphor_icon("ph.squares-four", color=DesignTokens.TEXT_MUTED).pixmap(16, 16))


__all__ = ["ModalField"]

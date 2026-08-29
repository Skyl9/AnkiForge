from typing import Any

from PySide6.QtWidgets import QHBoxLayout, QWidget

from ankiforge.ui.components import IconButton, StyledLineEdit
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon


class PasswordLineEdit(QWidget):
    """Champ de saisie sécurisé pour clés API avec bouton œil pour afficher/masquer."""

    def __init__(self, placeholder: str = "", initial_text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._is_visible: bool = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.edit = StyledLineEdit()
        self.edit.setEchoMode(StyledLineEdit.EchoMode.Password)
        self.edit.setPlaceholderText(placeholder)
        self.edit.setText(initial_text)
        layout.addWidget(self.edit, 1)

        self.btn_toggle = IconButton("ph.eye", tooltip="Afficher / Masquer la clé", size=26)
        self.btn_toggle.clicked.connect(self._toggle_visibility)
        layout.addWidget(self.btn_toggle)

    def _toggle_visibility(self) -> None:
        self._is_visible = not self._is_visible
        if self._is_visible:
            self.edit.setEchoMode(StyledLineEdit.EchoMode.Normal)
            self.btn_toggle.setIcon(load_phosphor_icon("ph.eye-slash", color=DesignTokens.ACCENT_PRIMARY))
        else:
            self.edit.setEchoMode(StyledLineEdit.EchoMode.Password)
            self.btn_toggle.setIcon(load_phosphor_icon("ph.eye", color=DesignTokens.TEXT_MUTED))

    def text(self) -> str:
        return self.edit.text().strip()

    def setText(self, text: str) -> None:
        self.edit.setText(text)

    def refresh_theme(self, profile: Any) -> None:
        icon_name = "ph.eye-slash" if self._is_visible else "ph.eye"
        color = profile.accent_primary if self._is_visible else profile.text_muted
        self.btn_toggle.setIcon(load_phosphor_icon(icon_name, color=color))

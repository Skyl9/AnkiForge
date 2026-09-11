"""
Dialogue modal de création d'un nouveau paquet Anki avec support hiérarchique.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import DeckModel
from ankiforge.repositories.deck_repository import DeckRepository
from ankiforge.ui.components.buttons import PrimaryButton, SecondaryButton
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class CreateDeckDialog(QDialog):
    """Dialogue modal permettant de saisir et créer un nouveau paquet ou sous-paquet Anki."""

    deck_created = Signal(int, str)  # (deck_id, deck_name)

    def __init__(self, initial_name: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Créer un nouveau paquet")
        self.setFixedWidth(460)
        self.setModal(True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)

        self.created_deck: DeckModel | None = None
        self._deck_repo = DeckRepository()

        self.setStyleSheet(f"""
            QDialog {{
                background-color: {DesignTokens.BG_PANEL};
                color: {DesignTokens.TEXT_PRIMARY};
                font-family: '{DesignTokens.FONT_MAIN}';
            }}
        """)

        self._setup_ui(initial_name)

    def _setup_ui(self, initial_name: str) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # En-tête
        header_layout = QHBoxLayout()
        header_layout.setSpacing(10)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(load_phosphor_icon("folder-plus", color=DesignTokens.ACCENT_PRIMARY).pixmap(24, 24))
        icon_lbl.setStyleSheet("border: none; background: transparent;")
        header_layout.addWidget(icon_lbl)

        title_vbox = QVBoxLayout()
        title_vbox.setSpacing(2)
        title_lbl = QLabel("Nouveau paquet Anki")
        title_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 14px; font-weight: bold; border: none;")
        subtitle_lbl = QLabel("Créez un paquet ou une arborescence de sous-paquets.")
        subtitle_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; border: none;")
        title_vbox.addWidget(title_lbl)
        title_vbox.addWidget(subtitle_lbl)
        header_layout.addLayout(title_vbox, 1)

        layout.addLayout(header_layout)

        # Champ Nom
        lbl_name = QLabel("Nom du paquet :")
        lbl_name.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 12px; font-weight: 600; border: none;")
        layout.addWidget(lbl_name)

        self.txt_name = QLineEdit()
        self.txt_name.setPlaceholderText("Ex: Sciences::Physique::Thermodynamique")
        self.txt_name.setText(initial_name)
        self.txt_name.setFixedHeight(34)
        self.txt_name.setStyleSheet(f"""
            QLineEdit {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 0 10px;
                color: {DesignTokens.TEXT_PRIMARY};
                font-size: 12px;
                font-family: '{DesignTokens.FONT_MAIN}';
            }}
            QLineEdit:focus {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        self.txt_name.textChanged.connect(self._on_name_changed)
        layout.addWidget(self.txt_name)

        # Indication hiérarchie
        lbl_hint = QLabel("💡 Utilisez le séparateur '::' pour imbriquer des sous-paquets.")
        lbl_hint.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; border: none; background: transparent;")
        layout.addWidget(lbl_hint)

        # Champ Description
        lbl_desc = QLabel("Description (optionnelle) :")
        lbl_desc.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 12px; font-weight: 600; border: none;")
        layout.addWidget(lbl_desc)

        self.txt_desc = QLineEdit()
        self.txt_desc.setPlaceholderText("Description courte du contenu du paquet...")
        self.txt_desc.setFixedHeight(34)
        self.txt_desc.setStyleSheet(f"""
            QLineEdit {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 0 10px;
                color: {DesignTokens.TEXT_PRIMARY};
                font-size: 12px;
                font-family: '{DesignTokens.FONT_MAIN}';
            }}
            QLineEdit:focus {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        layout.addWidget(self.txt_desc)

        # Message d'erreur / warning
        self.lbl_error = QLabel()
        self.lbl_error.setStyleSheet(f"color: {DesignTokens.COLOR_RED}; font-size: 11px; border: none;")
        self.lbl_error.hide()
        layout.addWidget(self.lbl_error)

        layout.addSpacing(6)

        # Boutons
        footer = QHBoxLayout()
        footer.setSpacing(8)

        self.btn_cancel = SecondaryButton("Annuler")
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_submit = PrimaryButton("Créer le paquet")
        self.btn_submit.setEnabled(bool(initial_name.strip()))
        self.btn_submit.clicked.connect(self._on_submit)

        footer.addStretch()
        footer.addWidget(self.btn_cancel)
        footer.addWidget(self.btn_submit)

        layout.addLayout(footer)

    def _on_name_changed(self, text: str) -> None:
        clean = text.strip()
        self.lbl_error.hide()
        self.btn_submit.setEnabled(bool(clean))

    def _on_submit(self) -> None:
        deck_name = self.txt_name.text().strip()
        if not deck_name:
            self.lbl_error.setText("Le nom du paquet ne peut pas être vide.")
            self.lbl_error.show()
            return

        desc = self.txt_desc.text().strip()

        try:
            deck = self._deck_repo.get_or_create_deck_hierarchical(deck_name, description=desc)
            self.created_deck = deck
            self.deck_created.emit(deck.id, deck.name)
            self.accept()
        except Exception as e:
            logger.error("Erreur lors de la création du paquet '%s': %s", deck_name, e)
            self.lbl_error.setText(f"Erreur : {e}")
            self.lbl_error.show()

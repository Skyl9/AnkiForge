from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ankiforge.ui.components import PrimaryButton, SecondaryButton
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon


class CreationHubWidget(QWidget):
    """
    Vue d'accueil et d'aiguillage du Studio de Création (Progressive Disclosure).
    Propose à l'utilisateur de choisir entre :
    1. Explorer les documents de sa bibliothèque
    2. Démarrer une saisie libre ou coller un extrait
    """

    open_free_text_requested = Signal()
    open_documents_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"background-color: {DesignTokens.BG_MAIN};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title_container = QVBoxLayout()
        title_container.setSpacing(4)
        title_container.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(load_phosphor_icon("ph.sparkle", color=DesignTokens.ACCENT_PRIMARY).pixmap(32, 32))
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_container.addWidget(icon_lbl)

        title_lbl = QLabel("Studio de Création AnkiForge")
        title_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 18px; font-weight: 700; border: none; background: transparent;")
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_container.addWidget(title_lbl)

        subtitle_lbl = QLabel("Choisissez un point de départ pour extraire et forger vos prochaines cartes mémoires :")
        subtitle_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 12px; border: none; background: transparent;")
        subtitle_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_container.addWidget(subtitle_lbl)

        layout.addLayout(title_container)

        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(16)
        cards_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Card 1: Explorer les Documents
        card_doc = QFrame()
        card_doc.setObjectName("cardDoc")
        card_doc.setFixedSize(300, 180)
        card_doc.setStyleSheet(f"""
            QFrame#cardDoc {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
            QFrame#cardDoc:hover {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        doc_l = QVBoxLayout(card_doc)
        doc_l.setContentsMargins(14, 14, 14, 14)
        doc_l.setSpacing(6)

        doc_icon = QLabel()
        doc_icon.setPixmap(load_phosphor_icon("ph.files", color=DesignTokens.COLOR_BLUE).pixmap(24, 24))
        doc_icon.setStyleSheet("background: transparent; border: none;")
        doc_l.addWidget(doc_icon)

        doc_title = QLabel("Explorer mes Documents")
        doc_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: 700; font-size: 13px; border: none; background: transparent;")
        doc_l.addWidget(doc_title)

        doc_desc = QLabel("Sélectionnez un cours (PDF, Markdown) ou importez de nouvelles sources pour forger des cartes.")
        doc_desc.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; border: none; background: transparent;")
        doc_desc.setWordWrap(True)
        doc_l.addWidget(doc_desc)

        doc_l.addStretch()

        btn_doc = PrimaryButton("Parcourir les Documents")
        btn_doc.setIcon(load_phosphor_icon("ph.folder-open", color="white"))
        btn_doc.clicked.connect(self.open_documents_requested.emit)
        doc_l.addWidget(btn_doc)

        cards_layout.addWidget(card_doc)

        # Card 2: Saisie Libre
        card_text = QFrame()
        card_text.setObjectName("cardText")
        card_text.setFixedSize(300, 180)
        card_text.setStyleSheet(f"""
            QFrame#cardText {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
            QFrame#cardText:hover {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        text_l = QVBoxLayout(card_text)
        text_l.setContentsMargins(14, 14, 14, 14)
        text_l.setSpacing(6)

        text_icon = QLabel()
        text_icon.setPixmap(load_phosphor_icon("ph.note-pencil", color=DesignTokens.COLOR_GREEN).pixmap(24, 24))
        text_icon.setStyleSheet("background: transparent; border: none;")
        text_l.addWidget(text_icon)

        text_title = QLabel("Saisie Libre / Presse-Papiers")
        text_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: 700; font-size: 13px; border: none; background: transparent;")
        text_l.addWidget(text_title)

        text_desc = QLabel("Collez ou écrivez directement vos notes, théorèmes ou résumés pour une extraction instantanée.")
        text_desc.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; border: none; background: transparent;")
        text_desc.setWordWrap(True)
        text_l.addWidget(text_desc)

        text_l.addStretch()

        btn_text = SecondaryButton("Ouvrir l'Éditeur Libre")
        btn_text.setIcon(load_phosphor_icon("ph.plus", color=DesignTokens.TEXT_PRIMARY))
        btn_text.clicked.connect(self.open_free_text_requested.emit)
        text_l.addWidget(btn_text)

        cards_layout.addWidget(card_text)
        layout.addLayout(cards_layout)

"""Dialogue d'aide interactive et antisèche pour les variables Jinja2 des prompts de Personas."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QSize, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ankiforge.services.ai.persona_templates import JINJA2_VARIABLE_DOCS, Jinja2VariableDoc
from ankiforge.ui.components import Badge, GlowLineEdit, PrimaryButton, SecondaryButton
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon


class VariableCard(QFrame):
    """Carte individuelle décrivant une variable Jinja2 et son exemple."""

    def __init__(self, doc: Jinja2VariableDoc, on_insert: Callable[[str], None], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.doc = doc
        self.on_insert = on_insert
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 6px;
            }}
            QFrame:hover {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        # En-tête : Variable code + Badge disponibilité + Bouton Insérer
        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        lbl_var = QLabel(doc.variable)
        lbl_var.setStyleSheet(f"""
            color: #38bdf8;
            font-family: '{DesignTokens.FONT_CODE}';
            font-size: 12.5px;
            font-weight: bold;
            background: transparent;
            border: none;
        """)
        top_row.addWidget(lbl_var)

        badge_scope = Badge(doc.scope_availability, variant="neutral")
        badge_scope.setFixedHeight(18)
        top_row.addWidget(badge_scope)
        top_row.addStretch()

        btn_insert = PrimaryButton("Insérer")
        btn_insert.setIcon(load_phosphor_icon("ph.plus", color="white"))
        btn_insert.setIconSize(QSize(12, 12))
        btn_insert.setFixedHeight(24)
        btn_insert.clicked.connect(lambda: self.on_insert(doc.variable))
        top_row.addWidget(btn_insert)

        layout.addLayout(top_row)

        # Description
        lbl_desc = QLabel(f"<b>{doc.label} :</b> {doc.description}")
        lbl_desc.setWordWrap(True)
        lbl_desc.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11.5px; background: transparent; border: none;")
        layout.addWidget(lbl_desc)

        # Exemple
        lbl_ex = QLabel(f"<i>Exemple de valeur injectée :</i> {doc.example}")
        lbl_ex.setWordWrap(True)
        lbl_ex.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; background: transparent; border: none;")
        layout.addWidget(lbl_ex)


class VariableHelperDialog(QDialog):
    """Dialogue affichant l'ensemble des variables Jinja2 disponibles avec explications et insertion 1-clic."""

    variable_inserted = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Antisèche des Variables de Prompt Jinja2")
        self.resize(700, 560)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {DesignTokens.BG_MAIN};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
        """)

        self._cards: list[tuple[VariableCard, Jinja2VariableDoc]] = []
        self._setup_ui()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # En-tête explicatif
        header_row = QHBoxLayout()
        header_row.setSpacing(8)
        lbl_icon = QLabel()
        lbl_icon.setPixmap(load_phosphor_icon("ph.sparkle", color=DesignTokens.ACCENT_PRIMARY).pixmap(20, 20))
        header_row.addWidget(lbl_icon)

        lbl_title = QLabel("Variables Contextuelles Dynamiques (Jinja2)")
        lbl_title.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {DesignTokens.TEXT_PRIMARY};")
        header_row.addWidget(lbl_title)
        header_row.addStretch()
        main_layout.addLayout(header_row)

        lbl_desc = QLabel(
            "Dans vos prompts système et étapes de pipelines DAG, les balises <code>{{ variable }}</code> "
            "sont automatiquement remplacées à l'exécution par les données réelles du document ou de l'étape."
        )
        lbl_desc.setWordWrap(True)
        lbl_desc.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11.5px;")
        main_layout.addWidget(lbl_desc)

        # Champ de filtrage
        self.edit_filter = GlowLineEdit(placeholder="Filtrer les variables (nom, usage, portée)...")
        self.edit_filter.setFixedHeight(28)
        self.edit_filter.textChanged.connect(self._apply_filter)
        main_layout.addWidget(self.edit_filter)

        # Zone déroulante des variables
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        cards_container = QWidget()
        self.cards_layout = QVBoxLayout(cards_container)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(8)

        for doc in JINJA2_VARIABLE_DOCS:
            card = VariableCard(doc, on_insert=self._on_insert_variable)
            self._cards.append((card, doc))
            self.cards_layout.addWidget(card)

        self.cards_layout.addStretch()
        scroll.setWidget(cards_container)
        main_layout.addWidget(scroll, 1)

        # Barre inférieure
        bottom_row = QHBoxLayout()
        bottom_row.addStretch()
        btn_close = SecondaryButton("Fermer")
        btn_close.clicked.connect(self.accept)
        bottom_row.addWidget(btn_close)
        main_layout.addLayout(bottom_row)

    def _on_insert_variable(self, var_code: str) -> None:
        self.variable_inserted.emit(var_code)
        self.accept()

    def _apply_filter(self, query: str) -> None:
        q = query.strip().lower()
        for card, doc in self._cards:
            match = not q or (q in doc.variable.lower() or q in doc.label.lower() or q in doc.description.lower() or q in doc.scope_availability.lower())
            card.setVisible(match)

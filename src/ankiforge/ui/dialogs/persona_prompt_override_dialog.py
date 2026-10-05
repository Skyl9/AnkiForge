"""Éditeur de prompt d'étape : la surface qui produit une surcharge locale de persona."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import PersonaModel
from ankiforge.services.ai.persona_override import (
    persona_label,
    persona_override_state,
    persona_prompt,
)
from ankiforge.ui.components import PrimaryButton, SecondaryButton, StyledTextEdit
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon


class PersonaPromptOverrideDialog(QDialog):
    """Éditeur de prompt dédié à une étape de pipeline.

    Ce n'est pas, et ce ne peut pas être, l'assistant de création d'agents : celui-là écrit
    une `PersonaModel` en base, ce qui violerait la promesse même de la surcharge (elle ne
    touche pas à l'agent). Cette boîte rend donc un **texte**, et c'est l'appelant qui décide
    de le figer dans la configuration de l'étape.

    Le titre annonce la portée, parce que l'auteur doit savoir *avant* d'écrire qu'il ne
    touche pas à un agent partagé : c'est la seule chose qu'aucun champ de saisie ne peut
    dire à sa place.
    """

    def __init__(
        self,
        *,
        persona: PersonaModel | None = None,
        step_title: str = "",
        current_text: str = "",
        config: dict[str, Any] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Surcharge locale du prompt de l'étape"))
        self.resize(680, 620)

        persona_name = persona_label(persona) or None
        header = step_title or (f"l'étape « {persona_name} »" if persona_name else "cette étape")
        subtitle = (
            f"Le prompt de l'agent « {persona_name} » ne sera pas modifié : cette surcharge ne vaut que pour {header}."
            if persona_name
            else f"Cette étape n'a pas d'agent : la surcharge ne vaut que pour {header}."
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        lbl_title = QLabel(self.tr("<b>Surcharge locale du prompt de l'étape</b>"))
        lbl_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 14px;")
        layout.addWidget(lbl_title)

        lbl_scope = QLabel(subtitle)
        lbl_scope.setWordWrap(True)
        lbl_scope.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")
        layout.addWidget(lbl_scope)

        # Le texte pré-rempli est la surcharge si elle existe, sinon le prompt de l'agent :
        # on édite ce qui partira réellement, en partant de la source que le vide désignerait.
        seeded = current_text.strip() or persona_prompt(persona)
        self.edit_prompt = StyledTextEdit()
        self.edit_prompt.setPlainText(seeded)
        self.edit_prompt.setMinimumHeight(300)
        self.edit_prompt.setPlaceholderText(self.tr("Laisser vide pour reprendre le prompt de l'agent au lieu de le figer."))
        self.edit_prompt.setStyleSheet(f"""
            QPlainTextEdit {{
                background: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                color: {DesignTokens.TEXT_PRIMARY};
                font-family: '{DesignTokens.FONT_CODE}';
                font-size: 12px;
                border-radius: 4px;
                padding: 8px;
            }}
        """)
        layout.addWidget(self.edit_prompt)

        # Rappel du figeage : l'auteur doit savoir, avant d'écrire, ce qu'il s'apprête à figer.
        state = persona_override_state(config or {}, persona)
        if state.active:
            lbl_frozen = QLabel(state.summary)
            lbl_frozen.setWordWrap(True)
            lbl_frozen.setStyleSheet(f"color: {DesignTokens.COLOR_YELLOW_TEXT if state.persona_changed_since_freeze else DesignTokens.TEXT_MUTED}; font-size: 11px;")
            layout.addWidget(lbl_frozen)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch()

        btn_cancel = QPushButton(self.tr("Annuler"))
        btn_cancel.setFixedHeight(30)
        btn_cancel.setFlat(True)
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                color: {DesignTokens.TEXT_MUTED};
                padding: 0 10px;
            }}
            QPushButton:hover {{ color: {DesignTokens.TEXT_PRIMARY}; }}
        """)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        self.btn_clear = SecondaryButton("Retirer la surcharge")
        self.btn_clear.setIconSize(QSize(14, 14))
        self.btn_clear.setFixedHeight(30)
        # Retirer est une décision explicite : hors du champ de surcharge, on ne le propose
        # que lorsqu'il y a effectivement quelque chose à retirer.
        self.btn_clear.setVisible(state.active)
        self.btn_clear.clicked.connect(self._on_clear_clicked)
        btn_row.addWidget(self.btn_clear)

        btn_save = PrimaryButton("Figer comme surcharge locale")
        btn_save.setIcon(load_phosphor_icon("ph.snowflake", color=DesignTokens.TEXT_ON_ACCENT))
        btn_save.setIconSize(QSize(14, 14))
        btn_save.setFixedHeight(30)
        btn_save.clicked.connect(self.accept)
        btn_row.addWidget(btn_save)

        layout.addLayout(btn_row)

    def _on_clear_clicked(self) -> None:
        """Retirer la surcharge : on rend un texte vide, l'appelant fera le ménage des métadonnées."""
        self.edit_prompt.setPlainText("")
        self.accept()

    def prompt_text(self) -> str:
        """Texte saisi par l'auteur, destiné à être figé dans la configuration de l'étape."""
        return self.edit_prompt.toPlainText().strip()

from typing import Any

from jinja2 import BaseLoader, Environment
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QLabel, QPlainTextEdit, QVBoxLayout, QWidget

from ankiforge.ui.components import SecondaryButton
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon


class AgentPromptPreviewDialog(QDialog):
    """Affiche la résolution dynamique du template Jinja2 du Persona avec des variables réalistes."""

    def __init__(self, template_str: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Aperçu du Prompt Interpolé (Jinja2)")
        self.resize(700, 500)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {DesignTokens.BG_MAIN};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
            QDialog QLabel {{
                background: transparent;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        lbl_header = QLabel("Ce que recevra le Modèle LLM (variables interpolées) :")
        lbl_header.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {DesignTokens.TEXT_PRIMARY};")
        layout.addWidget(lbl_header)

        rendered_text = ""
        try:
            env = Environment(loader=BaseLoader(), autoescape=False)  # nosec B701
            tpl = env.from_string(template_str)
            mock_vars: dict[str, Any] = {
                "text_source": "Soit A une matrice carrée n x n. A est diagonalisable s'il existe une base de vecteurs propres.",
                "generated_cards": [{"Front": "Définition diagonalisation", "Back": "Existe base de vecteurs propres"}],
                "last_output": "Cartes générées avec succès.",
                "plan_cours": "1. Définition\n2. Valeurs propres\n3. Sous-espaces propres",
            }
            mock_state: dict[str, Any] = {
                "initial_prompt": "Créer 5 flashcards sur la diagonalisation matricielle.",
                "variables": mock_vars,
            }
            rendered_text = tpl.render(
                state=mock_state,
                text_source=mock_vars["text_source"],
                last_output=mock_vars["last_output"],
                fields=["Front", "Back"],
                retrieved_chunks=["Extrait 1 : Valeurs propres et polynôme caractéristique."],
                item="Section 1 : Définition des endomorphismes",
                initial_prompt=mock_state["initial_prompt"],
            )
        except Exception as e:
            rendered_text = f"❌ Erreur de syntaxe Jinja2 dans le template :\n{e}"

        edit_rendered = QPlainTextEdit()
        edit_rendered.setReadOnly(True)
        edit_rendered.setPlainText(rendered_text)
        edit_rendered.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                color: #38bdf8;
                font-family: '{DesignTokens.FONT_CODE}';
                font-size: 12px;
                line-height: 1.4;
                padding: 10px;
                border-radius: 6px;
            }}
        """)
        layout.addWidget(edit_rendered, 1)

        btn_close = SecondaryButton("Fermer l'aperçu")
        btn_close.setIcon(load_phosphor_icon("ph.check-circle", color=DesignTokens.TEXT_PRIMARY))
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignmentFlag.AlignRight)

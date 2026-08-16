"""
Modale interactive de Validation Humaine (Copilote Intentionnel).
S'affiche lorsqu'un pipeline DAG atteint une étape de type HUMAN_VALIDATION.
Permet à l'utilisateur de valider, corriger ou enrichir les données intermédiaires (ex: Plan de cours).
"""

import json
import logging
from typing import Optional

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ankiforge.services.ai.state import PipelineRunState
from ankiforge.ui.components import DangerButton, PrimaryButton
from ankiforge.ui.theme import DesignTokens

logger = logging.getLogger(__name__)


class HumanValidationDialog(QDialog):
    """Boîte de dialogue interactive pour la validation humaine au cours de l'exécution du DAG."""

    def __init__(self, state: PipelineRunState, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("🤝 Copilote Intentionnel — Validation Humaine")
        self.resize(680, 520)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {DesignTokens.BG_PANEL};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
        """)

        self.state = state
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # 1. En-tête
        header_lbl = QLabel("<h2>🤝 Validation Requise du Plan / Concepts</h2>")
        header_lbl.setStyleSheet(f"color: {DesignTokens.ACCENT_PRIMARY}; margin: 0; padding: 0;")
        layout.addWidget(header_lbl)

        desc_lbl = QLabel(
            "L'IA a terminé l'étape d'analyse préliminaire et a extrait les concepts clés ci-dessous.\n"
            "Vous pouvez vérifier, modifier, ajouter ou supprimer des éléments avant de déclencher la génération des cartes :"
        )
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 12px; line-height: 1.4;")
        layout.addWidget(desc_lbl)

        # 2. Éditeur de texte / JSON
        self.editor = QTextEdit()
        self.editor.setStyleSheet(f"""
            QTextEdit {{
                background-color: {DesignTokens.BG_INPUT};
                color: {DesignTokens.TEXT_PRIMARY};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
                padding: 12px;
                font-family: 'JetBrains Mono', 'Fira Code', Menlo, monospace;
                font-size: 13px;
                line-height: 1.5;
            }}
            QTextEdit:focus {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)

        last_out = self.state.get_variable("last_output", {})
        if isinstance(last_out, (dict, list)):
            self.editor.setPlainText(json.dumps(last_out, ensure_ascii=False, indent=2))
        else:
            self.editor.setPlainText(str(last_out))

        layout.addWidget(self.editor, 1)

        # 3. Barre de boutons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        self.btn_cancel = DangerButton("Annuler le Pipeline", ghost=True)
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        btn_layout.addStretch()

        self.btn_validate = PrimaryButton("Valider & Reprendre le Pipeline ▶")
        self.btn_validate.clicked.connect(self._on_validate_clicked)
        btn_layout.addWidget(self.btn_validate)

        layout.addLayout(btn_layout)

    def _on_validate_clicked(self) -> None:
        """Parse le contenu modifié et met à jour l'état avant de valider la boîte de dialogue."""
        raw_content = self.editor.toPlainText().strip()
        try:
            parsed = json.loads(raw_content)
            self.state.set_variable("last_output", parsed)

            # Si le JSON contient une liste de concepts ou de cartes, on alimente map_items
            if isinstance(parsed, dict) and "concepts_cles" in parsed and isinstance(parsed["concepts_cles"], list):
                self.state.set_variable("map_items", parsed["concepts_cles"])
            elif isinstance(parsed, dict) and "concepts" in parsed and isinstance(parsed["concepts"], list):
                self.state.set_variable("map_items", parsed["concepts"])
            elif isinstance(parsed, list):
                self.state.set_variable("map_items", parsed)

        except Exception:
            # Fallback en texte brut si ce n'est pas un JSON valide
            self.state.set_variable("last_output", raw_content)
            lines = [line.strip() for line in raw_content.splitlines() if line.strip()]
            if lines:
                self.state.set_variable("map_items", lines)

        self.accept()

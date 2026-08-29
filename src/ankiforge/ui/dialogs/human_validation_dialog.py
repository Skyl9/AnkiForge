"""
Modale interactive de Validation Humaine (Copilote Intentionnel).
S'affiche lorsqu'un pipeline DAG atteint une étape de type HUMAN_VALIDATION.
Permet à l'utilisateur de valider, corriger ou enrichir les données intermédiaires (ex: Plan de cours).
"""

import json
import logging
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from ankiforge.services.ai.state import PipelineRunState
from ankiforge.ui.components import DangerButton, PrimaryButton, SecondaryButton
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class HumanValidationDialog(QDialog):
    """Boîte de dialogue interactive pour la validation humaine au cours de l'exécution du DAG."""

    def __init__(self, state: PipelineRunState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.state = state
        self.setWindowTitle("Copilote Intentionnel — Validation Humaine")
        self.resize(720, 540)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {DesignTokens.BG_MAIN};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
            QDialog QLabel {{
                background: transparent;
            }}
        """)

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Récupération de la configuration personnalisée éventuelle de l'étape
        cfg: dict[str, Any] = self.state.get_variable("human_validation_config", {})
        title_text = cfg.get("human_title") or "Validation Requise du Plan / Concepts"
        message_text = cfg.get("human_message") or (
            "L'IA a terminé l'étape d'analyse préliminaire et a extrait les éléments ci-dessous.\n"
            "Vous pouvez vérifier, modifier, ajouter ou supprimer des éléments avant de poursuivre l'exécution du workflow :"
        )

        # 1. En-tête avec Icône Phosphor
        header_row = QHBoxLayout()
        header_row.setSpacing(10)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(load_phosphor_icon("ph.pause-circle", color=DesignTokens.COLOR_YELLOW).pixmap(24, 24))
        header_row.addWidget(icon_lbl)

        header_lbl = QLabel(f"<b>{title_text}</b>")
        header_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 15px;")
        header_row.addWidget(header_lbl, 1)

        layout.addLayout(header_row)

        desc_lbl = QLabel(message_text)
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 12px; line-height: 1.4;")
        layout.addWidget(desc_lbl)

        # 2. Éditeur de texte / JSON
        self.editor = QPlainTextEdit()
        self.editor.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {DesignTokens.BG_INPUT};
                color: {DesignTokens.TEXT_PRIMARY};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 12px;
                font-family: {DesignTokens.FONT_CODE};
                font-size: {DesignTokens.FONT_SIZE_CODE}px;
                line-height: 1.5;
            }}
            QPlainTextEdit:focus {{
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

        self.btn_cancel = DangerButton("Interrompre le Workflow", ghost=True)
        self.btn_cancel.setIcon(load_phosphor_icon("ph.x", color=DesignTokens.COLOR_RED))
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        btn_layout.addStretch()

        self.btn_format_json = SecondaryButton("Formater JSON")
        self.btn_format_json.setIcon(load_phosphor_icon("ph.code", color=DesignTokens.TEXT_PRIMARY))
        self.btn_format_json.clicked.connect(self._format_json)
        btn_layout.addWidget(self.btn_format_json)

        self.btn_validate = PrimaryButton("Valider & Reprendre le Pipeline")
        self.btn_validate.setIcon(load_phosphor_icon("ph.play", color="white"))
        self.btn_validate.clicked.connect(self._on_validate_clicked)
        btn_layout.addWidget(self.btn_validate)

        layout.addLayout(btn_layout)

    def _format_json(self) -> None:
        """Formate le JSON présent dans l'éditeur s'il est valide."""
        try:
            parsed = json.loads(self.editor.toPlainText().strip())
            self.editor.setPlainText(json.dumps(parsed, ensure_ascii=False, indent=2))
        except Exception:
            # Ne pas modifier si texte brut non-JSON
            pass  # nosec B110

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

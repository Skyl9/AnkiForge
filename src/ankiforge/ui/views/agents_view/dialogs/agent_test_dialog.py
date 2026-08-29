import logging
from typing import Any, Optional

from jinja2 import BaseLoader, Environment
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import PersonaModel
from ankiforge.services.ai.base import MockProvider
from ankiforge.ui.components import PrimaryButton, SecondaryButton
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class AgentTestDialog(QDialog):
    """Dialogue pour tester l'exécution unitaire d'un Persona avec un texte source."""

    def __init__(self, persona: PersonaModel, ai_manager: Optional[Any] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.persona = persona
        self.ai_manager = ai_manager
        self.setWindowTitle(f"Test d'Agent : {persona.name}")
        self.resize(680, 520)
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

        lbl_input = QLabel("Texte source d'entrée (User Prompt) :")
        lbl_input.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {DesignTokens.TEXT_PRIMARY};")
        layout.addWidget(lbl_input)

        self.edit_user_input = QTextEdit()
        self.edit_user_input.setPlaceholderText("Saisissez un extrait de cours pour tester la génération de cet agent...")
        self.edit_user_input.setText("La photosynthèse est le processus bioénergétique qui permet aux plantes de synthétiser de la matière organique grâce à la lumière du soleil.")
        self.edit_user_input.setMaximumHeight(90)
        self.edit_user_input.setStyleSheet(f"background: {DesignTokens.BG_INPUT}; border: 1px solid {DesignTokens.BORDER_COLOR}; color: {DesignTokens.TEXT_PRIMARY}; border-radius: 4px; padding: 6px;")
        layout.addWidget(self.edit_user_input)

        lbl_output = QLabel("Réponse du Modèle IA :")
        lbl_output.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {DesignTokens.TEXT_PRIMARY};")
        layout.addWidget(lbl_output)

        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setStyleSheet(f"background: {DesignTokens.BG_INPUT}; border: 1px solid {DesignTokens.BORDER_COLOR}; color: #38bdf8; font-family: monospace; font-size: 12px;")
        layout.addWidget(self.output_text, 1)

        h_btn = QHBoxLayout()
        self.btn_run = PrimaryButton("Exécuter le Test")
        self.btn_run.setIcon(load_phosphor_icon("ph.play", color="white"))
        self.btn_run.clicked.connect(self._run_test)
        btn_close = SecondaryButton("Fermer")
        btn_close.clicked.connect(self.accept)
        h_btn.addWidget(self.btn_run)
        h_btn.addStretch()
        h_btn.addWidget(btn_close)
        layout.addLayout(h_btn)

    def _run_test(self) -> None:
        self.output_text.clear()
        self.output_text.append("🧪 Exécution du Persona en cours...")
        user_input = self.edit_user_input.toPlainText().strip()

        provider = None
        if getattr(self.persona, "llm_config", None) and self.ai_manager and hasattr(self.ai_manager, "create_provider_from_config"):
            try:
                provider = self.ai_manager.create_provider_from_config(self.persona.llm_config)
            except Exception as e:
                logger.warning("Impossible de créer le provider dédié : %s", e)

        if not provider:
            provider = MockProvider()

        try:
            env = Environment(loader=BaseLoader(), autoescape=False)  # nosec B701
            tpl = env.from_string(str(self.persona.system_prompt or ""))
            rendered_sys = tpl.render(
                text_source=user_input,
                fields=["Front", "Back"],
                retrieved_chunks=[],
                last_output="",
            )

            res = provider.generate(
                system_prompt=rendered_sys,
                user_prompt=user_input,
                response_format=getattr(self.persona, "output_format", "json") or "json",
            )
            self.output_text.clear()
            self.output_text.append(f"<b>Prompt Système Interpolé :</b>\n{rendered_sys}\n")
            self.output_text.append(f"<b>Réponse du Modèle :</b>\n{res.content if hasattr(res, 'content') else str(res)}")
        except Exception as e:
            self.output_text.append(f"❌ Erreur d'exécution : {e}")

import json
from typing import Any

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import PipelineModel, PipelineStepModel
from ankiforge.services.ai.base import MockProvider
from ankiforge.services.ai.orchestrator import PipelineOrchestrator
from ankiforge.services.ai.state import PipelineRunState
from ankiforge.services.tools.tool_service import ToolService
from ankiforge.ui.components import PrimaryButton, SecondaryButton
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.views.pipelines_view.constants import STEP_TYPES_META
from ankiforge.utils.icon_loader import load_phosphor_icon


class StepTestDialog(QDialog):
    """Dialogue modal pour tester l'exécution unitaire d'une étape spécifique."""

    def __init__(self, step_data: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.step_data = step_data
        step_type = step_data.get("type", "LLM_PROMPT")
        meta = STEP_TYPES_META.get(step_type, STEP_TYPES_META["LLM_PROMPT"])

        self.setWindowTitle(f"Test d'Étape : {step_data.get('custom_title', meta['default_title'])}")
        self.resize(650, 480)
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

        lbl_desc = QLabel("Simulation de l'étape sur un état en mémoire :")
        lbl_desc.setFont(QFont(DesignTokens.FONT_MAIN, 11, QFont.Weight.Bold))
        layout.addWidget(lbl_desc)

        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setStyleSheet(f"background: {DesignTokens.BG_INPUT}; border: 1px solid {DesignTokens.BORDER_COLOR}; color: #38bdf8; font-family: monospace; font-size: 12px;")
        layout.addWidget(self.output_text, 1)

        h_btn = QHBoxLayout()
        btn_run = PrimaryButton("Lancer la simulation")
        btn_run.setIcon(load_phosphor_icon("ph.play", color="white"))
        btn_run.clicked.connect(self._run_simulation)
        btn_close = SecondaryButton("Fermer")
        btn_close.clicked.connect(self.accept)
        h_btn.addWidget(btn_run)
        h_btn.addStretch()
        h_btn.addWidget(btn_close)
        layout.addLayout(h_btn)

    def _run_simulation(self) -> None:
        self.output_text.clear()
        self.output_text.append("🧪 Démarrage de la simulation d'étape...")

        stype = self.step_data.get("type", "LLM_PROMPT")
        cfg = self.step_data.get("config", {})

        state = PipelineRunState(initial_prompt="Exemple de cours d'informatique.")
        state.set_variable("text_source", "La complexité temporelle du tri fusion est O(n log n).")
        state.set_variable("generated_cards", [{"Front": "Complexité du tri fusion ?", "Back": "O(n log n)"}])

        if stype == "LLM_PROMPT":
            persona = self.step_data.get("persona")
            prompt_override = cfg.get("prompt_override")
            raw_prompt = prompt_override or (persona.prompt_template if persona else "Extrais 3 flashcards du texte.")
            self.output_text.append(f"Prompt appliqué :\n{raw_prompt}\n")
            mock = MockProvider()
            res = mock.generate("Système", raw_prompt)
            self.output_text.append(f"Réponse simulée de l'IA :\n{res.content}")

        elif stype == "RAG_RETRIEVAL":
            self.output_text.append("Recherche RAG vectorielle (Top-K = {})".format(cfg.get("top_k", 5)))
            self.output_text.append("Fragments trouvés : 3 chunks simulés depuis FAISS.")

        elif stype == "PYTHON_TOOL":
            tool_name = cfg.get("tool_name", "clean_html_latex")
            res = ToolService.execute_tool(tool_name, state)
            self.output_text.append(f"Exécution outil '{tool_name}' : {res}")

        elif stype == "HUMAN_VALIDATION":
            self.output_text.append("Interruption Copilote simulée : 'Plan validé par l'utilisateur'")


class PipelineRunDialog(QDialog):
    """Dialogue de test en direct du pipeline complet avec logs et suivi pas à pas."""

    def __init__(self, pipeline: PipelineModel, steps: list[dict[str, Any]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.pipeline = pipeline
        self.steps = steps
        self.setWindowTitle(f"Test en direct : {pipeline.name}")
        self.resize(750, 520)
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

        lbl_top = QLabel(f"Exécution du pipeline DAG ({len(steps)} étapes) :")
        lbl_top.setFont(QFont(DesignTokens.FONT_MAIN, 12, QFont.Weight.Bold))
        layout.addWidget(lbl_top)

        self.console = QPlainTextEdit()
        self.console.setReadOnly(True)
        self.console.setStyleSheet(f"background: {DesignTokens.BG_INPUT}; border: 1px solid {DesignTokens.BORDER_COLOR}; color: #38bdf8; font-family: monospace; font-size: 12px;")
        layout.addWidget(self.console, 1)

        h_btn = QHBoxLayout()
        self.btn_start = PrimaryButton("Démarrer l'exécution")
        self.btn_start.setIcon(load_phosphor_icon("ph.play", color="white"))
        self.btn_start.clicked.connect(self._start_run)
        self.btn_close = SecondaryButton("Fermer")
        self.btn_close.clicked.connect(self.accept)
        h_btn.addWidget(self.btn_start)
        h_btn.addStretch()
        h_btn.addWidget(self.btn_close)
        layout.addLayout(h_btn)

    def _start_run(self) -> None:
        self.btn_start.setEnabled(False)
        self.console.appendPlainText("🚀 Initialisation du Moteur DAG...")

        state = PipelineRunState(initial_prompt="Introduction à l'algèbre linéaire.")
        state.set_variable("text_source", "Une matrice est un tableau rectangulaire de nombres réels ou complexes.")

        step_models: list[PipelineStepModel] = []
        for idx, s in enumerate(self.steps, start=1):
            cfg_json = json.dumps(s.get("config", {}))
            sm = PipelineStepModel(
                pipeline=self.pipeline,
                persona=s.get("persona"),
                step_type=s.get("type", "LLM_PROMPT"),
                step_order=idx,
                failure_behavior=s.get("failure_behavior", "stop"),
                config_data=cfg_json,
            )
            step_models.append(sm)

        self.orchestrator = PipelineOrchestrator(
            initial_state=state,
            steps=step_models,
        )
        self.orchestrator.signals.step_started.connect(self._on_step_started)
        self.orchestrator.signals.step_completed.connect(self._on_step_completed)
        self.orchestrator.signals.pipeline_finished.connect(self._on_finished)
        self.orchestrator.signals.error_occurred.connect(self._on_error)
        self.orchestrator.run()

    def _on_step_started(self, step_order: int, desc: str) -> None:
        self.console.appendPlainText(f"\n▶ [{step_order}] {desc}")

    def _on_step_completed(self, step_order: int, state: PipelineRunState) -> None:
        self.console.appendPlainText(f"  ✅ Étape {step_order} terminée avec succès.")

    def _on_finished(self, state: PipelineRunState) -> None:
        cards = state.get_variable("generated_cards", [])
        self.console.appendPlainText(f"\n🏁 Pipeline terminé avec succès ! ({len(cards)} cartes générées)")
        self.btn_start.setEnabled(True)

    def _on_error(self, err: str) -> None:
        self.console.appendPlainText(f"\n❌ Erreur : {err}")
        self.btn_start.setEnabled(True)

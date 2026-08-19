#!/usr/bin/env python3
"""
Testeur Graphique Interactif (GUI Qt) du Moteur DAG d'AnkiForge.
Interface PySide6 autonome permettant de visualiser en temps réel l'exécution
des étapes du DAG, les barres de progression Map-Reduce, la modale de validation
humaine interactive et le tableau des flashcards générées.

Usage:
    python script/test_manual_dag_gui.py
    ou
    uv run python script/test_manual_dag_gui.py
"""

import json
import sys
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, QThreadPool, Slot
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    LLMConfigModel,
    NoteModel,
    NoteTypeModel,
    PersonaModel,
    PipelineModel,
    PipelineStepModel,
    db,
)
from ankiforge.services.ai.base import LLMProvider
from ankiforge.services.ai.orchestrator import PipelineOrchestrator
from ankiforge.services.ai.state import PipelineRunState
from ankiforge.ui.components import Badge, DangerButton, IdePanel, PrimaryButton, SecondaryButton
from ankiforge.ui.theme import DesignTokens


class MockGuiProvider(LLMProvider):
    """Fournisseur IA simulé pour tests graphiques instantanés."""

    def generate(self, system_prompt: str, user_prompt: str | list[dict[str, Any]], response_format: str = "json") -> str:
        prompt_str = (system_prompt + " " + str(user_prompt)).lower()

        if "plan" in prompt_str or "architecte" in prompt_str:
            return json.dumps(
                {
                    "titre_cours": "Cours de Physique Quantique",
                    "concepts_cles": [
                        "Dualité Onde-Corpuscule de De Broglie",
                        "Principe d'Incertitude d'Heisenberg",
                        "Équation d'onde de Schrödinger",
                        "Effet Tunnel et Applications",
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )

        if "item" in prompt_str or "générateur" in prompt_str:
            return json.dumps(
                {
                    "cards": [
                        {
                            "Front": f"Énoncez et expliquez le concept : {str(user_prompt)[:60]}",
                            "Back": "Formulation physique rigoureuse et implications expérimentales associées.",
                        }
                    ]
                },
                ensure_ascii=False,
                indent=2,
            )

        if response_format == "json":
            return json.dumps({"cards": [{"Front": "Question test", "Back": "Réponse test"}]})
        return "Résultat textuel de traitement DAG."


class HumanValidationDialog(QDialog):
    """Modale interactive s'affichant lors de l'étape HUMAN_VALIDATION."""

    def __init__(self, state: PipelineRunState, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("🤝 Copilote Intentionnel — Validation Humaine")
        self.resize(600, 480)
        self.setStyleSheet(f"background-color: {DesignTokens.BG_PANEL}; color: {DesignTokens.TEXT_PRIMARY};")

        self.state = state
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        header_lbl = QLabel("<h2>Validation du Plan Conceptuel</h2>")
        header_lbl.setStyleSheet(f"color: {DesignTokens.ACCENT_PRIMARY};")
        layout.addWidget(header_lbl)

        desc_lbl = QLabel(
            "L'IA a terminé l'analyse documentaire et a extrait les concepts clés ci-dessous.\n"
            "Vous pouvez modifier, supprimer ou ajouter des éléments avant de déclencher la génération massive (Map-Reduce) :"
        )
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED};")
        layout.addWidget(desc_lbl)

        self.editor = QTextEdit()
        self.editor.setStyleSheet(f"""
            QTextEdit {{
                background-color: {DesignTokens.BG_DARK};
                color: {DesignTokens.TEXT_PRIMARY};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
                padding: 10px;
                font-family: monospace;
                font-size: 13px;
            }}
        """)

        last_out = state.get_variable("last_output", {})
        if isinstance(last_out, (dict, list)):
            self.editor.setPlainText(json.dumps(last_out, ensure_ascii=False, indent=2))
        else:
            self.editor.setPlainText(str(last_out))

        layout.addWidget(self.editor, 1)

        # Boutons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_cancel = SecondaryButton("Annuler le Pipeline")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_validate = PrimaryButton("Valider & Reprendre le DAG ▶")
        self.btn_validate.clicked.connect(self._on_validate)
        btn_layout.addWidget(self.btn_validate)

        layout.addLayout(btn_layout)

    def _on_validate(self):
        try:
            parsed = json.loads(self.editor.toPlainText())
            self.state.set_variable("last_output", parsed)
            if isinstance(parsed, dict) and "concepts_cles" in parsed:
                self.state.set_variable("map_items", parsed["concepts_cles"])
        except Exception:
            self.state.set_variable("last_output", self.editor.toPlainText())
        self.accept()


class DagVisualTesterWindow(QMainWindow):
    """Fenêtre principale du banc de test visuel DAG."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("AnkiForge — Banc de Test Visuel du Moteur DAG")
        self.resize(1000, 700)
        self.setStyleSheet(f"background-color: {DesignTokens.BG_DARK}; color: {DesignTokens.TEXT_PRIMARY};")

        self.thread_pool = QThreadPool.globalInstance()
        self.orchestrator: Optional[PipelineOrchestrator] = None

        self._init_db()
        self._build_ui()

    def _init_db(self):
        db.init(":memory:")
        db.connect()
        db.create_tables([
            DeckModel,
            NoteTypeModel,
            NoteModel,
            CardModel,
            PersonaModel,
            PipelineModel,
            PipelineStepModel,
            LLMConfigModel,
        ])

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(18, 18, 18, 18)
        main_layout.setSpacing(14)

        # En-tête
        header_layout = QHBoxLayout()
        title_lbl = QLabel("<h2>🛠️ Banc d'Essai du Moteur DAG d'Orchestration</h2>")
        title_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY};")
        header_layout.addWidget(title_lbl)

        header_layout.addStretch()

        self.btn_run = PrimaryButton("▶ Démarrer le Pipeline DAG")
        self.btn_run.clicked.connect(self._run_pipeline)
        header_layout.addWidget(self.btn_run)

        self.btn_stop = DangerButton("⏹ Annuler")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._cancel_pipeline)
        header_layout.addWidget(self.btn_stop)

        main_layout.addLayout(header_layout)

        # Barre de progression
        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 4px;
                text-align: center;
                background-color: {DesignTokens.BG_PANEL};
                color: {DesignTokens.TEXT_PRIMARY};
                height: 20px;
            }}
            QProgressBar::chunk {{
                background-color: {DesignTokens.ACCENT_PRIMARY};
                border-radius: 3px;
            }}
        """)
        self.progress_bar.setValue(0)
        main_layout.addWidget(self.progress_bar)

        self.status_lbl = QLabel("Statut : Prêt à lancer.")
        self.status_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-weight: bold;")
        main_layout.addWidget(self.status_lbl)

        # Séparateur : Gauche = Logs des étapes, Droite = Tableau des Cartes Générées
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Panneau de gauche : Stepper & Logs
        left_panel = IdePanel("Journal d'Exécution DAG")
        left_layout = QVBoxLayout()
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet(f"""
            QTextEdit {{
                background-color: {DesignTokens.BG_PANEL};
                color: {DesignTokens.COLOR_GREEN};
                border: none;
                font-family: monospace;
                font-size: 12px;
            }}
        """)
        left_layout.addWidget(self.log_text)
        left_panel.content_layout.addLayout(left_layout)
        splitter.addWidget(left_panel)

        # Panneau de droite : Tableau des Cartes
        right_panel = IdePanel("Flashcards Générées dans l'État")
        right_layout = QVBoxLayout()
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Recto (Front)", "Verso (Back)"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {DesignTokens.BG_PANEL};
                color: {DesignTokens.TEXT_PRIMARY};
                border: none;
                gridline-color: {DesignTokens.BORDER_COLOR};
            }}
            QHeaderView::section {{
                background-color: {DesignTokens.BG_DARK};
                color: {DesignTokens.TEXT_MUTED};
                font-weight: bold;
                padding: 6px;
                border: 1px solid {DesignTokens.BORDER_COLOR};
            }}
        """)
        right_layout.addWidget(self.table)
        right_panel.content_layout.addLayout(right_layout)
        splitter.addWidget(right_panel)

        splitter.setSizes([450, 550])
        main_layout.addWidget(splitter, 1)

    def _log(self, text: str):
        self.log_text.append(text)

    def _run_pipeline(self):
        self.btn_run.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.log_text.clear()
        self.table.setRowCount(0)
        self.progress_bar.setValue(0)
        self.status_lbl.setText("Statut : ⚙️ Initialisation du pipeline...")

        # Création des étapes du DAG
        pipeline = PipelineModel.create(name="DAG Test GUI")

        step1 = PipelineStepModel.create(pipeline=pipeline, step_order=1, step_type="RAG_RETRIEVAL")

        p2 = PersonaModel.create(name="Architecte", system_prompt="Plan du cours", output_format="json")
        step2 = PipelineStepModel.create(pipeline=pipeline, persona=p2, step_order=2, step_type="LLM_PROMPT")

        step3 = PipelineStepModel.create(pipeline=pipeline, step_order=3, step_type="HUMAN_VALIDATION")

        p4 = PersonaModel.create(name="Rédacteur", system_prompt="Flashcards pour: {{ item }}", output_format="json")
        step4 = PipelineStepModel.create(pipeline=pipeline, persona=p4, step_order=4, step_type="MAP_REDUCE")

        p5 = PersonaModel.create(name="Linter", system_prompt="Contrôle qualité", output_format="json")
        step5 = PipelineStepModel.create(pipeline=pipeline, persona=p5, step_order=5, step_type="LLM_PROMPT")

        initial_state = PipelineRunState(initial_prompt="Physique Quantique Fondamentale")
        initial_state.set_variable(
            "text_source",
            "La dualité onde-corpuscule unifie les aspects ondulatoires et corpusculaires. "
            "Le principe d'incertitude de Heisenberg limite la précision simultanée de la position et de l'impulsion.",
        )

        provider = MockGuiProvider()
        self.orchestrator = PipelineOrchestrator(
            pipeline_id=pipeline.id,
            initial_state=initial_state,
            ai_provider=provider,
        )

        # Connexions des signaux
        self.orchestrator.signals.step_started.connect(self._on_step_started)
        self.orchestrator.signals.step_progress.connect(self._on_step_progress)
        self.orchestrator.signals.step_completed.connect(self._on_step_completed)
        self.orchestrator.signals.human_validation_required.connect(self._on_human_validation)
        self.orchestrator.signals.pipeline_finished.connect(self._on_pipeline_finished)
        self.orchestrator.signals.error_occurred.connect(self._on_error)
        self.orchestrator.signals.cancelled.connect(self._on_cancelled)

        self.thread_pool.start(self.orchestrator)

    def _cancel_pipeline(self):
        if self.orchestrator:
            self._log("⚠️ Demande d'annulation...")
            self.orchestrator.cancel()

    @Slot(int, str)
    def _on_step_started(self, order: int, desc: str):
        self._log(f"▶ [{order}] {desc}")
        self.status_lbl.setText(f"Statut : {desc}")
        self.progress_bar.setValue(int((order - 1) / 5 * 100))

    @Slot(int, int, str)
    def _on_step_progress(self, curr: int, total: int, msg: str):
        self._log(f"   ↳ {msg}")

    @Slot(int, object)
    def _on_step_completed(self, order: int, state: PipelineRunState):
        self._log(f"✔ Étape {order} terminée avec succès.")

    @Slot(object)
    def _on_human_validation(self, state: PipelineRunState):
        self._log("\n⏸️ INTERRUPTION : Validation Humaine en cours...")
        self.status_lbl.setText("Statut : ⏸️ En attente de validation utilisateur (Copilote)...")

        dialog = HumanValidationDialog(state, self)
        res = dialog.exec()
        if res == QDialog.DialogCode.Accepted:
            self._log("✔ Validation confirmée par l'utilisateur. Reprise du DAG.")
            if self.orchestrator:
                self.orchestrator.resume(state)
        else:
            self._log("❌ Annulation demandée dans la boîte de dialogue.")
            if self.orchestrator:
                self.orchestrator.cancel()

    @Slot(object)
    def _on_pipeline_finished(self, state: PipelineRunState):
        self.progress_bar.setValue(100)
        self.status_lbl.setText("Statut : 🎉 Pipeline terminé avec succès !")
        self._log("\n🎉 Exécution du DAG complétée !")

        cards = state.get_variable("generated_cards", [])
        self._log(f"Total Cartes générées : {len(cards)}")

        self.table.setRowCount(len(cards))
        for row, card in enumerate(cards):
            front = card.get("Front", card.get("front", ""))
            back = card.get("Back", card.get("back", ""))
            self.table.setItem(row, 0, QTableWidgetItem(str(front)))
            self.table.setItem(row, 1, QTableWidgetItem(str(back)))

        self.btn_run.setEnabled(True)
        self.btn_stop.setEnabled(False)

    @Slot(str)
    def _on_error(self, err_msg: str):
        self._log(f"\n❌ ERREUR : {err_msg}")
        self.status_lbl.setText(f"Erreur : {err_msg}")
        QMessageBox.critical(self, "Erreur DAG", err_msg)
        self.btn_run.setEnabled(True)
        self.btn_stop.setEnabled(False)

    @Slot()
    def _on_cancelled(self):
        self._log("\n⏹️ Pipeline annulé.")
        self.status_lbl.setText("Statut : Pipeline annulé.")
        self.btn_run.setEnabled(True)
        self.btn_stop.setEnabled(False)


def main():
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)
    window = DagVisualTesterWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

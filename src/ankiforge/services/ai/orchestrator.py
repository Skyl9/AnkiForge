import time
from typing import Optional
from PySide6.QtCore import QObject, Signal, QRunnable, Slot

from ankiforge.database.models import PipelineStepModel, LLMConfigModel
from ankiforge.services.ai.state import PipelineRunState
from ankiforge.services.ai.rag_service import RAGService


class PipelineWorkerSignals(QObject):
    """Signaux Qt émis par le Worker (Orchestrateur) vers l'UI."""

    step_started = Signal(int, str)  # step_order, description
    step_completed = Signal(int, object)  # step_order, state_dict
    human_validation_required = Signal(object)  # state pour l'UI
    pipeline_finished = Signal(object)  # state final
    error_occurred = Signal(str)


class PipelineOrchestrator(QRunnable):
    """
    Cœur du Moteur d'Orchestration.
    Exécute le DAG (Directed Acyclic Graph) de manière asynchrone (QRunnable).
    """

    def __init__(self, pipeline_id: int, initial_state: PipelineRunState):
        super().__init__()
        self.pipeline_id = pipeline_id
        self.state = initial_state
        self.signals = PipelineWorkerSignals()
        self._is_paused = False
        self._is_cancelled = False

    @Slot()
    def run(self):
        """Démarre l'exécution du pipeline."""
        try:
            # 1. Charger la première étape du pipeline
            # On suppose que l'étape avec step_order=1 est la racine
            current_step = PipelineStepModel.get_or_none((PipelineStepModel.pipeline == self.pipeline_id) & (PipelineStepModel.step_order == 1))

            while current_step is not None and not self._is_cancelled:
                # Émettre un signal pour mettre à jour l'UI (Loader, logs...)
                self.signals.step_started.emit(current_step.step_order, f"Étape {current_step.step_order} : {current_step.step_type}")

                self.state.current_step_id = current_step.id

                # ==========================================
                # ROUTEUR DE TYPES D'ÉTAPES
                # ==========================================
                if current_step.step_type == "LLM_PROMPT":
                    self._execute_llm_prompt(current_step)

                elif current_step.step_type == "RAG_RETRIEVAL":
                    self._execute_rag_retrieval(current_step)

                elif current_step.step_type == "MAP_REDUCE":
                    self._execute_map_reduce(current_step)

                elif current_step.step_type == "HUMAN_VALIDATION":
                    self._execute_human_validation()
                    # La boucle se met en pause ici
                    while self._is_paused and not self._is_cancelled:
                        time.sleep(0.5)  # Attente active légère (Thread non-bloquant pour l'UI)

                # TODO: Gérer l'échec (on_failure_step)
                # Pour l'instant, on suit le chemin on_success_step
                self.signals.step_completed.emit(current_step.step_order, self.state)

                if current_step.on_success_step:
                    current_step = current_step.on_success_step
                else:
                    current_step = None  # Fin du DAG

            if not self._is_cancelled:
                self.signals.pipeline_finished.emit(self.state)

        except Exception as e:
            self.state.add_error(str(e))
            self.signals.error_occurred.emit(str(e))

    # ==========================================
    # MÉTHODES DE TRAITEMENT (STUBS)
    # ==========================================
    def _execute_llm_prompt(self, step: PipelineStepModel) -> None:
        """Exécute un prompt classique sur Ollama/OpenAI."""
        # Implémentation réelle : Appel API LLM avec step.persona
        time.sleep(2)  # Simulation API
        self.state.set_variable(f"result_step_{step.step_order}", "Generated text by LLM")

    def _execute_rag_retrieval(self, step: PipelineStepModel) -> None:
        """Fouille l'index FAISS du document."""
        doc_id = str(self.state.document_id)
        if not doc_id or doc_id == "0":
            # Si pas de doc_id, on crée un index temporaire avec le text_source
            text_source = self.state.get_variable("text_source")
            if text_source:
                doc_id = "temp_doc"

                llm_config = LLMConfigModel.select().first()
                if not llm_config:
                    self.state.retrieved_chunks.append("Erreur: Aucun moteur IA configuré pour le RAG.")
                    return

                rag = RAGService(llm_config)
                rag.create_index(doc_id, text_source)

                # Requête = persona system prompt ou une variable
                query = step.persona.system_prompt if step.persona else "Résumé"
                results = rag.search(doc_id, query, top_k=3)
                self.state.retrieved_chunks.extend(results)
                return

        self.state.retrieved_chunks.append("Chunk de texte pertinent depuis FAISS.")

    def _execute_map_reduce(self, step: PipelineStepModel) -> None:
        """Applique une IA sur une liste (ex: 100 cartes à analyser)."""
        # Implémentation réelle : Lancement de N threads en parallèle
        time.sleep(3)
        self.state.set_variable("map_reduce_results", ["Card 1 fixed", "Card 2 fixed"])

    def _execute_human_validation(self) -> None:
        """Alerte l'UI qu'une intervention humaine est requise."""
        self._is_paused = True
        self.signals.human_validation_required.emit(self.state)

    # ==========================================
    # CONTRÔLES EXTERNES (APPELÉS PAR L'UI)
    # ==========================================
    def resume(self, modified_state: Optional[PipelineRunState] = None) -> None:
        """Reprend l'exécution (appelé par l'UI après validation)."""
        if modified_state:
            self.state = modified_state
        self._is_paused = False

    def cancel(self) -> None:
        """Stoppe définitivement le pipeline."""
        self._is_cancelled = True
        self._is_paused = False

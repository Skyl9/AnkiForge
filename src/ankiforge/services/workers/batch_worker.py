from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from PySide6.QtCore import QThread, Signal

from ankiforge.database.models import PersonaModel, PipelineStepModel
from ankiforge.services.ai.flexible_service import AIManager
from ankiforge.services.ai.orchestrator import PipelineOrchestrator, PipelineRunState
from ankiforge.services.ai.utils import extract_cards_from_data

logger = logging.getLogger(__name__)


@dataclass
class BatchTaskPayload:
    """
    Conteneur de données brutes pour une tâche de traitement par lots.
    Évite les accès directs à la base de données dans le thread secondaire.
    """

    task_index: int
    doc_id: int
    doc_title: str
    doc_content: str
    deck_id: int
    deck_name: str
    model_id: int
    model_name: str
    note_type_fields: list[str]
    note_type_templates: list[dict[str, Any]]
    pipeline_id: int
    pipeline_name: str
    llm_id: int
    llm_config: dict[str, Any]
    chunk_strategy: str = "auto"
    use_vision: bool = False
    auto_validation: bool = True
    temperature: float = 0.7
    max_tokens: int = 16384
    extra_metadata: dict[str, Any] = field(default_factory=dict)


class BatchWorker(QThread):
    """
    Worker d'exécution par lots s'appuyant sur le moteur DAG PipelineOrchestrator.

    Traite séquentiellement chaque document de la file d'attente, notifie en direct
    l'UI de la progression spécifique à chaque tâche, et isole les erreurs éventuelles
    pour ne pas interrompre l'ensemble du lot.
    """

    # Signaux individuels par tâche
    task_started = Signal(int, str)  # task_idx, doc_title
    task_progress = Signal(int, int, str)  # task_idx, progress_pct, step_detail
    task_completed = Signal(int, list, int)  # task_idx, prepared_notes, cards_count
    task_failed = Signal(int, str)  # task_idx, error_message

    # Signaux globaux du batch
    log = Signal(str, str)  # level ("INFO", "SUCCESS", "WARN", "ERROR"), message
    batch_finished = Signal(int, int, int)  # success_count, error_count, total_cards
    cancelled = Signal()

    # Rétrocompatibilité avec les anciens signaux
    progress_val = Signal(int)
    progress_text = Signal(str)
    finished = Signal(int, int)
    error = Signal(str)
    batch_data_ready = Signal(list, int, int, int)  # notes, deck_id, model_id, doc_id

    def __init__(self, ai_provider: Any = None, tasks: list[BatchTaskPayload] | None = None) -> None:
        super().__init__()
        self.ai_provider = ai_provider
        self.tasks: list[BatchTaskPayload] = tasks or []
        self._is_cancelled = False
        self._active_orchestrator: PipelineOrchestrator | None = None

    def cancel(self) -> None:
        """Demande l'arrêt immédiat et propre de tous les traitements en cours."""
        logger.info("Demande d'annulation reçue pour BatchWorker.")
        self._is_cancelled = True
        if self._active_orchestrator is not None:
            self._active_orchestrator.cancel()

    def run(self) -> None:
        """Exécute séquentiellement chaque tâche de la file d'attente."""
        total_tasks = len(self.tasks)
        if total_tasks == 0:
            self.batch_finished.emit(0, 0, 0)
            self.finished.emit(0, 0)
            return

        success_count = 0
        error_count = 0
        total_cards_generated = 0

        self.log.emit("INFO", f"🚀 Démarrage du traitement par lots ({total_tasks} document(s) dans la file)...")
        self.progress_val.emit(0)

        for current_idx, task in enumerate(self.tasks):
            if self._is_cancelled:
                logger.info("Traitement par lots interrompu par l'utilisateur.")
                self.log.emit("WARN", "⏹ Traitement par lots interrompu par l'utilisateur.")
                self.cancelled.emit()
                return

            self.task_started.emit(task.task_index, task.doc_title)
            self.progress_text.emit(f"Traitement : {task.doc_title} ({current_idx + 1}/{total_tasks})...")
            self.log.emit(
                "INFO",
                f"\n{'═' * 50}\n▶ JOB {current_idx + 1}/{total_tasks} : '{task.doc_title}'\n  Paquet : {task.deck_name} | Modèle : {task.model_name} | Pipeline : {task.pipeline_name}\n{'═' * 50}",
            )

            task_cards_count = 0

            try:
                # 1. Instanciation du fournisseur LLM configuré
                llm_cfg = task.llm_config
                provider_name = str(llm_cfg.get("provider", "openai"))
                model_id = str(llm_cfg.get("model_id", "default"))
                api_key = str(llm_cfg.get("api_key", ""))
                max_tokens = task.max_tokens or int(llm_cfg.get("max_tokens", 16384))

                active_provider = AIManager.create_provider(
                    provider_name=provider_name,
                    model_id=model_id,
                    api_key=api_key,
                    max_tokens=max_tokens,
                )

                # 2. Chargement des étapes du pipeline DAG
                steps = list(PipelineStepModel.select().where(PipelineStepModel.pipeline == task.pipeline_id).order_by(PipelineStepModel.step_order.asc()))

                if not steps:
                    # Pipeline de repli automatique si le pipeline n'a aucune étape
                    logger.warning("Pipeline %d sans étapes, utilisation d'un prompt standard.", task.pipeline_id)
                    persona = PersonaModel.select().first()
                    default_prompt = (
                        "Tu es un expert pédagogique de création de cartes Anki.\n"
                        "Analyse le texte suivant et génère des cartes mémoire de haute qualité atomiques.\n\n"
                        "TEXTE SOURCE :\n{{ text_source }}\n\n"
                        "MODÈLE CIBLE : {{ note_type }}\n"
                        "CHAMPS REQUIS : {{ fields_str }}\n\n"
                        "Génère ta réponse au format JSON contenant un tableau de cartes sous la clé 'notes' ou directement un tableau d'objets."
                    )
                    steps = [
                        PipelineStepModel(
                            pipeline_id=task.pipeline_id,
                            persona=persona,
                            step_type="LLM_PROMPT",
                            step_order=1,
                            config_data=json.dumps({"prompt_template": default_prompt, "output_format": "json"}),
                        )
                    ]

                total_steps = len(steps)

                # 3. Préparation de l'état partagé du DAG
                initial_state = PipelineRunState(
                    document_id=task.doc_id,
                    initial_prompt="",
                    variables={
                        "input_text": task.doc_content,
                        "deck_id": task.deck_id,
                        "model_id": task.model_id,
                        "auto_validation": task.auto_validation,
                    },
                )
                fields_str = ", ".join(f'"{f}"' for f in task.note_type_fields)
                first_f = task.note_type_fields[0] if task.note_type_fields else "Front"
                second_f = task.note_type_fields[1] if len(task.note_type_fields) > 1 else "Back"

                initial_state.set_variable("fields", task.note_type_fields)
                initial_state.set_variable("fields_str", fields_str)
                initial_state.set_variable("first_field", first_f)
                initial_state.set_variable("second_field", second_f)
                initial_state.set_variable("target_deck", task.deck_name)
                initial_state.set_variable("note_type", task.model_name)
                initial_state.set_variable("use_vision", task.use_vision)

                # 4. Instanciation de l'orchestrateur DAG
                orchestrator = PipelineOrchestrator(
                    pipeline_id=task.pipeline_id,
                    initial_state=initial_state,
                    steps=steps,
                    ai_provider=active_provider,
                )
                self._active_orchestrator = orchestrator

                # Connexion des signaux de progression
                orchestrator.signals.step_started.connect(lambda order, desc, t=task, tot=total_steps: self._on_step_started(t, order, tot, desc))
                orchestrator.signals.step_progress.connect(lambda cur, tot, detail, t=task: self._on_step_progress(t, cur, tot, detail))
                orchestrator.signals.step_completed.connect(lambda order, st, t=task: self._on_step_completed(t, order, st))
                orchestrator.signals.human_validation_required.connect(lambda st, t=task, orch=orchestrator: self._on_human_validation_required(t, orch, st))

                # Exécution synchrone dans ce thread
                orchestrator.run()

                if self._is_cancelled:
                    self.task_failed.emit(task.task_index, "Annulé par l'utilisateur")
                    self.cancelled.emit()
                    return

                # 5. Extraction des cartes générées depuis l'état final
                final_state = orchestrator.state
                if final_state.errors:
                    err_summary = "; ".join(final_state.errors)
                    raise RuntimeError(f"Erreur du pipeline : {err_summary}")

                cards_raw = final_state.get_variable("generated_cards") or final_state.get_variable("map_reduce_results") or final_state.get_variable("last_output") or []
                extracted_cards = extract_cards_from_data(cards_raw)

                # Nettoyage et normalisation des champs
                prepared_notes = self._normalize_notes(extracted_cards, task.note_type_fields)
                task_cards_count = len(prepared_notes)

                if task_cards_count > 0:
                    success_count += 1
                    total_cards_generated += task_cards_count
                    self.task_completed.emit(task.task_index, prepared_notes, task_cards_count)
                    self.batch_data_ready.emit(prepared_notes, task.deck_id, task.model_id, task.doc_id)
                    self.log.emit("SUCCESS", f"✅ JOB {current_idx + 1}/{total_tasks} validé : {task_cards_count} cartes extraites pour '{task.doc_title}'.")
                else:
                    error_count += 1
                    msg = f"Aucune carte exploitable extraite pour '{task.doc_title}'."
                    self.task_failed.emit(task.task_index, msg)
                    self.log.emit("WARN", f"⚠️ JOB {current_idx + 1}/{total_tasks} : {msg}")

            except Exception as e:
                error_count += 1
                err_msg = str(e)
                logger.exception("Erreur lors du traitement de la tâche %d (%s) : %s", task.task_index, task.doc_title, e)
                self.task_failed.emit(task.task_index, err_msg)
                self.log.emit("ERROR", f"❌ JOB {current_idx + 1}/{total_tasks} Échec : {err_msg}")

            finally:
                self._active_orchestrator = None

            progress_pct = int(((current_idx + 1) / total_tasks) * 100)
            self.progress_val.emit(progress_pct)

        self.log.emit(
            "SUCCESS",
            f"\n{'═' * 50}\n🏁 Traitement par lots terminé !\n  Total réussis : {success_count} | Échecs : {error_count} | Cartes générées : {total_cards_generated}\n{'═' * 50}",
        )
        self.batch_finished.emit(success_count, error_count, total_cards_generated)
        self.finished.emit(success_count, error_count)

    def _on_step_started(self, task: BatchTaskPayload, step_order: int, total_steps: int, desc: str) -> None:
        pct = int(((step_order - 1) / max(1, total_steps)) * 100)
        self.task_progress.emit(task.task_index, pct, f"Étape {step_order}/{total_steps}...")
        self.log.emit("INFO", f"  [{task.doc_title}] ▶ {desc}")

    def _on_step_progress(self, task: BatchTaskPayload, cur: int, tot: int, detail: str) -> None:
        pct = int((cur / max(1, tot)) * 100)
        self.task_progress.emit(task.task_index, pct, detail)

    def _on_step_completed(self, task: BatchTaskPayload, step_order: int, state: PipelineRunState) -> None:
        dur = 0.0
        if state.execution_history:
            last = state.execution_history[-1]
            if last.get("step_order") == step_order:
                dur = float(last.get("duration_sec", 0.0))
        self.log.emit("SUCCESS", f"  [{task.doc_title}] ✅ Étape {step_order} terminée ({dur:.2f}s)")

    def _on_human_validation_required(self, task: BatchTaskPayload, orchestrator: PipelineOrchestrator, state: PipelineRunState) -> None:
        self.log.emit("INFO", f"  [{task.doc_title}] ⏩ Validation humaine auto-validée (mode batch activé).")
        orchestrator.resume(state)

    @staticmethod
    def _normalize_notes(cards: list[dict[str, Any]], expected_fields: list[str]) -> list[dict[str, Any]]:
        """Normalise les dictionnaires de cartes pour correspondre strictement aux champs attendus."""
        prepared: list[dict[str, Any]] = []
        for card_data in cards:
            if not isinstance(card_data, dict):
                continue

            cleaned: dict[str, str] = {}
            lower_card = {str(k).lower().strip(): v for k, v in card_data.items()}
            raw_vals = list(card_data.values())

            for i, f in enumerate(expected_fields):
                f_lower = f.lower().strip()
                if f_lower in lower_card:
                    val = lower_card[f_lower]
                elif i < len(raw_vals):
                    val = raw_vals[i]
                else:
                    val = ""

                if isinstance(val, list):
                    val_str = "<br>".join(str(item) for item in val)
                elif val is not None:
                    val_str = str(val)
                else:
                    val_str = ""

                cleaned[f] = val_str

            prepared.append(cleaned)
        return prepared

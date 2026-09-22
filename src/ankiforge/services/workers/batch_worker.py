from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from PySide6.QtCore import QThread, Signal

from ankiforge.database.models import PersonaModel, PipelineStepModel
from ankiforge.services.ai.flexible_service import AIManager
from ankiforge.services.ai.orchestrator import PipelineOrchestrator, PipelineRunState
from ankiforge.services.ai.utils import extract_cards_from_data, normalize_card_fields
from ankiforge.services.batch.models import BatchTaskSnapshot, BatchTaskStatus

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
    process_full_document: bool = False
    source_chunks: list[dict[str, Any]] = field(default_factory=list)
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
    task_review_ready = Signal(int, list)  # task_idx, prepared_notes (mode staging)
    task_accepted = Signal(int, int)  # task_idx, cards_count (mode auto-validation)
    task_state_changed = Signal(str, str)

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

    def __init__(
        self,
        ai_provider: Any = None,
        tasks: list[BatchTaskPayload | BatchTaskSnapshot] | None = None,
        resume_incomplete: bool = False,
    ) -> None:
        super().__init__()
        self.ai_provider = ai_provider
        self.tasks: list[BatchTaskPayload | BatchTaskSnapshot] = tasks or []
        self.resume_incomplete = resume_incomplete
        self._is_cancelled = False
        self._active_orchestrator: PipelineOrchestrator | None = None

    def cancel(self) -> None:
        """Demande l'arrêt immédiat et propre de tous les traitements en cours."""
        logger.info("Demande d'annulation reçue pour BatchWorker.")
        self._is_cancelled = True
        if self._active_orchestrator is not None:
            self._active_orchestrator.cancel()

    @staticmethod
    def can_retry(task: BatchTaskSnapshot) -> bool:
        """Return whether a failed scope still has a manual retry available."""
        return task.status == BatchTaskStatus.FAILED and task.attempt < 3

    def run(self) -> None:
        """Exécute séquentiellement chaque tâche de la file d'attente."""
        if self.tasks and all(isinstance(task, BatchTaskSnapshot) for task in self.tasks):
            self._run_scope_snapshots([task for task in self.tasks if isinstance(task, BatchTaskSnapshot)])
            return
        legacy_tasks = [task for task in self.tasks if isinstance(task, BatchTaskPayload)]
        total_tasks = len(legacy_tasks)
        if total_tasks == 0:
            self.batch_finished.emit(0, 0, 0)
            self.finished.emit(0, 0)
            return

        success_count = 0
        error_count = 0
        total_cards_generated = 0

        self.log.emit("INFO", f"🚀 Démarrage du traitement par lots ({total_tasks} document(s) dans la file)...")
        self.progress_val.emit(0)

        for current_idx, task in enumerate(legacy_tasks):
            if self._is_cancelled:
                logger.info("Traitement par lots interrompu par l'utilisateur.")
                self.log.emit("WARN", "⏹ Traitement par lots interrompu par l'utilisateur.")
                self.cancelled.emit()
                return

            if self.resume_incomplete and task.extra_metadata.get("status") in ("Succès", "success", "Terminé"):
                success_count += 1
                task_cards = int(task.extra_metadata.get("cards_count", 0))
                total_cards_generated += task_cards
                self.log.emit("INFO", f"  [{task.doc_title}] ⏩ Tâche déjà validée précédemment ({task_cards} cartes), sautée.")
                continue

            self.task_started.emit(task.task_index, task.doc_title)
            self.progress_text.emit(f"Traitement : {task.doc_title} ({current_idx + 1}/{total_tasks})...")
            self.log.emit(
                "INFO",
                f"\n{'═' * 50}\n▶ JOB {current_idx + 1}/{total_tasks} : '{task.doc_title}'\n  Paquet : {task.deck_name} | Modèle : {task.model_name} | Pipeline : {task.pipeline_name}\n{'═' * 50}",
            )

            task_cards_count = 0
            task_errors = 0

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

                fields_str = ", ".join(f'"{f}"' for f in task.note_type_fields)
                first_f = task.note_type_fields[0] if task.note_type_fields else "Front"
                second_f = task.note_type_fields[1] if len(task.note_type_fields) > 1 else "Back"
                source_chunks = task.source_chunks if task.source_chunks else [{"content": task.doc_content, "index": 0}]
                prepared_notes: list[dict[str, Any]] = []

                for chunk_index, chunk in enumerate(source_chunks):
                    if self._is_cancelled:
                        self.task_failed.emit(task.task_index, "Annulé par l'utilisateur")
                        self.cancelled.emit()
                        return

                    chunk_content = str(chunk.get("content", "")).strip()
                    if not chunk_content:
                        task_errors += 1
                        self.log.emit("WARN", f"⚠️ [{task.doc_title}] Chunk {chunk_index + 1}/{len(source_chunks)} vide, ignoré.")
                        continue

                    self.task_progress.emit(
                        task.task_index,
                        int((chunk_index / max(1, len(source_chunks))) * 100),
                        f"Chunk {chunk_index + 1}/{len(source_chunks)}",
                    )
                    try:
                        initial_state = PipelineRunState(
                            document_id=task.doc_id,
                            initial_prompt=chunk_content,
                            variables={
                                "input_text": chunk_content,
                                "text_source": chunk_content,
                                "document_chunk": chunk_content,
                                "source_chunk": chunk_content,
                                "source_chunk_index": chunk_index,
                                "source_chunk_id": chunk.get("id"),
                                "source_chunk_hash": chunk.get("content_hash"),
                                "source_heading_path": chunk.get("heading_path"),
                                "source_page_number": chunk.get("page_number"),
                                "deck_id": task.deck_id,
                                "model_id": task.model_id,
                                "auto_validation": task.auto_validation,
                                "strict_source_grounding": task.process_full_document,
                            },
                        )
                        initial_state.set_variable("fields", task.note_type_fields)
                        initial_state.set_variable("fields_str", fields_str)
                        initial_state.set_variable("first_field", first_f)
                        initial_state.set_variable("second_field", second_f)
                        initial_state.set_variable("target_deck", task.deck_name)
                        initial_state.set_variable("note_type", task.model_name)
                        initial_state.set_variable("use_vision", task.use_vision)

                        orchestrator = PipelineOrchestrator(
                            pipeline_id=task.pipeline_id,
                            initial_state=initial_state,
                            steps=steps,
                            ai_provider=active_provider,
                        )
                        self._active_orchestrator = orchestrator
                        orchestrator.signals.step_started.connect(lambda order, desc, t=task, tot=total_steps: self._on_step_started(t, order, tot, desc))
                        orchestrator.signals.step_progress.connect(lambda cur, tot, detail, t=task: self._on_step_progress(t, cur, tot, detail))
                        orchestrator.signals.step_completed.connect(lambda order, st, t=task: self._on_step_completed(t, order, st))
                        orchestrator.signals.human_validation_required.connect(lambda st, t=task, orch=orchestrator: self._on_human_validation_required(t, orch, st))
                        orchestrator.run()

                        if orchestrator.state.errors:
                            raise RuntimeError("; ".join(orchestrator.state.errors))
                        cards_raw = orchestrator.state.get_variable("generated_cards") or orchestrator.state.get_variable("map_reduce_results") or orchestrator.state.get_variable("last_output") or []
                        extracted_cards = extract_cards_from_data(cards_raw)
                        for note in normalize_card_fields(extracted_cards, task.note_type_fields):
                            note["_source_chunk_id"] = chunk.get("id")
                            note["_source_chunk_hash"] = chunk.get("content_hash")
                            note["_source_heading_path"] = chunk.get("heading_path")
                            note["_source_page_number"] = chunk.get("page_number")
                            note["_documentation_enabled"] = True
                            prepared_notes.append(note)
                    except Exception as chunk_error:
                        task_errors += 1
                        self.log.emit("ERROR", f"❌ [{task.doc_title}] Chunk {chunk_index + 1}/{len(source_chunks)} : {chunk_error}")
                    finally:
                        self._active_orchestrator = None

                prepared_notes = self._deduplicate_notes(prepared_notes, task.note_type_fields)
                task_cards_count = len(prepared_notes)

                if task_cards_count > 0:
                    success_count += 1
                    total_cards_generated += task_cards_count
                    self.task_completed.emit(task.task_index, prepared_notes, task_cards_count)
                    self.batch_data_ready.emit(prepared_notes, task.deck_id, task.model_id, task.doc_id)
                    if task.auto_validation:
                        # Mode validation automatique : les cartes sont prêtes pour la
                        # persistance immédiate, aucune revue staging nécessaire.
                        self.task_accepted.emit(task.task_index, task_cards_count)
                    else:
                        # Mode staging : placer les cartes en revue pour validation manuelle.
                        self.task_review_ready.emit(task.task_index, prepared_notes)
                    status = "avec erreurs de chunks" if task_errors else "validé"
                    self.log.emit("SUCCESS", f"✅ JOB {current_idx + 1}/{total_tasks} {status} : {task_cards_count} cartes extraites pour '{task.doc_title}'.")
                else:
                    error_count += 1
                    msg = f"Aucune carte exploitable extraite pour '{task.doc_title}' ({task_errors} chunk(s) en erreur)."
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

    def _run_scope_snapshots(self, tasks: list[BatchTaskSnapshot]) -> None:
        """Execute the new scope-based protocol without persisting review results."""
        success_count = 0
        error_count = 0
        total_cards = 0
        provider_cache: dict[tuple[str, str, int], Any] = {}

        for index, task in enumerate(tasks):
            if self._is_cancelled:
                for rem in tasks[index:]:
                    if rem.status not in (BatchTaskStatus.ACCEPTED, BatchTaskStatus.REVIEW):
                        rem.status = BatchTaskStatus.CANCELLED
                        self.task_state_changed.emit(rem.task_id, rem.status.value)
                self.cancelled.emit()
                break

            if self.resume_incomplete and task.status in (BatchTaskStatus.ACCEPTED, BatchTaskStatus.REVIEW):
                success_count += 1
                total_cards += len(task.cards)
                continue

            task.status = BatchTaskStatus.RUNNING
            task.attempt += 1
            self.task_state_changed.emit(task.task_id, task.status.value)
            self.task_started.emit(index, task.scope.scope_title)
            try:
                config = task.config
                llm_cfg = config.llm_config
                provider_key = (str(llm_cfg.get("provider", "openai")), str(llm_cfg.get("model_id", "default")), config.max_tokens)
                provider = self.ai_provider or provider_cache.get(provider_key)
                if provider is None:
                    provider = AIManager.create_provider(
                        provider_name=provider_key[0],
                        model_id=provider_key[1],
                        api_key=str(llm_cfg.get("api_key", "")),
                        max_tokens=config.max_tokens,
                    )
                    provider_cache[provider_key] = provider

                steps = list(PipelineStepModel.select().where(PipelineStepModel.pipeline == config.pipeline_id).order_by(PipelineStepModel.step_order.asc()))
                if not steps:
                    raise RuntimeError(f"Le pipeline {config.pipeline_id} ne contient aucune étape.")
                state = PipelineRunState(
                    document_id=task.scope.document_id,
                    initial_prompt=task.scope.content,
                    variables={
                        "input_text": task.scope.content,
                        "text_source": task.scope.content,
                        "source_scope_text": task.scope.content,
                        "source_blocks": [block.as_dict() for block in task.scope.blocks],
                        "source_scope_hash": task.scope.scope_hash,
                        "source_heading_path": ", ".join(filter(None, (block.heading_path for block in task.scope.blocks))),
                        "source_page_numbers": [block.page_number for block in task.scope.blocks if block.page_number is not None],
                        "deck_id": config.deck_id,
                        "model_id": config.model_id,
                        "auto_validation": config.auto_validation,
                        "strict_source_grounding": config.strict_source_grounding,
                    },
                )
                state.set_variable("fields", list(config.note_type_fields))
                state.set_variable("fields_str", ", ".join(config.note_type_fields))
                state.set_variable("target_deck", config.deck_name)
                state.set_variable("note_type", config.model_name)
                orchestrator = PipelineOrchestrator(
                    pipeline_id=config.pipeline_id,
                    initial_state=state,
                    steps=steps,
                    ai_provider=provider,
                )
                self._active_orchestrator = orchestrator
                total_steps = len(steps)
                orchestrator.signals.step_started.connect(lambda order, desc, i=index, tot=total_steps: self.task_progress.emit(i, int(((order - 1) / max(1, tot)) * 100), f"Étape {order}/{tot}..."))
                orchestrator.signals.step_progress.connect(lambda cur, tot, detail, i=index: self.task_progress.emit(i, int((cur / max(1, tot)) * 100), detail))
                orchestrator.run()
                if state.errors:
                    raise RuntimeError("; ".join(state.errors))
                raw_cards = state.get_variable("generated_cards") or state.get_variable("map_reduce_results") or state.get_variable("last_output") or []
                task.cards = self._deduplicate_notes(normalize_card_fields(extract_cards_from_data(raw_cards), list(config.note_type_fields)), list(config.note_type_fields))
                scope_heading_path = ", ".join(filter(None, (block.heading_path for block in getattr(task.scope, "blocks", []))))
                scope_page = next((int(b.page_number) for b in getattr(task.scope, "blocks", []) if b.page_number is not None), None)
                for card in task.cards:
                    card.setdefault("_source_heading_path", scope_heading_path)
                    card.setdefault("_source_page_number", scope_page)
                    card.setdefault("_source_chunk_id", None)
                    card.setdefault("_documentation_enabled", True)
                if config.auto_validation:
                    # Mode validation automatique : persistance immédiate, sans staging.
                    task.status = BatchTaskStatus.ACCEPTED
                    success_count += 1
                    total_cards += len(task.cards)
                    self.task_accepted.emit(index, len(task.cards))
                    self.task_completed.emit(index, task.cards, len(task.cards))
                    self.task_state_changed.emit(task.task_id, task.status.value)
                else:
                    # Mode staging : cartes prêtes pour la revue utilisateur.
                    task.status = BatchTaskStatus.REVIEW
                    success_count += 1
                    total_cards += len(task.cards)
                    self.task_review_ready.emit(index, task.cards)
                    self.task_completed.emit(index, task.cards, len(task.cards))
                    self.task_state_changed.emit(task.task_id, task.status.value)
            except Exception as exc:
                task.status = BatchTaskStatus.FAILED
                task.error = str(exc)
                error_count += 1
                self.task_failed.emit(index, task.error)
                self.task_state_changed.emit(task.task_id, task.status.value)
                logger.exception("Échec de la portée Batch %s", task.task_id)
            finally:
                self._active_orchestrator = None
                self.progress_val.emit(int(((index + 1) / max(1, len(tasks))) * 100))

        self.batch_finished.emit(success_count, error_count, total_cards)
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
    def _deduplicate_notes(notes: list[dict[str, Any]], expected_fields: list[str]) -> list[dict[str, Any]]:
        """Supprime les doublons exacts en conservant la première provenance."""
        seen: set[tuple[str, ...]] = set()
        unique: list[dict[str, Any]] = []
        for note in notes:
            key = tuple(str(note.get(field, "")).strip().casefold() for field in expected_fields)
            if not any(key):
                continue
            if key in seen:
                continue
            seen.add(key)
            unique.append(note)
        return unique

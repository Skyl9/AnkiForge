import json
import logging
import uuid
from typing import Any

from PySide6.QtCore import QThread, Signal
from jinja2 import Template

from ankiforge.database.models import db, LLMConfigModel, PipelineStepModel, PipelineModel, NoteTypeModel, DeckModel, DocumentModel, NoteModel, NoteVersionModel, CardModel
from ankiforge.services.ai.flexible_service import AIManager
from ankiforge.utils.anki_renderer import get_max_cloze_index
from ankiforge.utils.chunker import smart_chunk_text
from ankiforge.utils.paths import get_app_data_dir
from ankiforge.utils.vision_utils import strip_image_tags, prepare_multimodal_payload

logger = logging.getLogger(__name__)


class BatchWorker(QThread):
    """
    Thread de traitement par lots asynchrone.
    Découpe les documents selon la stratégie choisie et exécute les pipelines IA successifs.
    """

    progress_val = Signal(int)
    progress_text = Signal(str)
    log = Signal(str)
    finished = Signal(int, int)
    error = Signal(str)
    cancelled = Signal()

    def __init__(self, ai_provider: Any, tasks: list[dict[str, Any]]):
        """
        Initialise le travailleur de traitement par lots.

        Args:
            ai_provider (Any): Le fournisseur IA par défaut (peut être écrasé par la tâche).
            tasks (list[dict]): Liste des tâches configurées depuis l'interface utilisateur.
        """
        super().__init__()
        self.ai_provider = ai_provider
        self.tasks = tasks
        self._is_cancelled = False

    def cancel(self) -> None:
        """Lève le drapeau d'annulation pour interrompre le traitement au prochain cycle."""
        self._is_cancelled = True

    @staticmethod
    def _clean_json(raw_text: str) -> str:
        """Nettoie les balises markdown entourant potentiellement un JSON brut."""
        clean = raw_text.strip()
        if clean.startswith("```json"):
            clean = clean[7:-3].strip()
        elif clean.startswith("```"):
            clean = clean[3:-3].strip()
        return clean

    def run(self) -> None:
        try:
            total_tasks = len(self.tasks)
            success_count = 0
            error_count = 0

            self.progress_val.emit(0)

            for task_idx, task in enumerate(self.tasks):
                if self._is_cancelled:
                    logger.info("Traitement par lots annulé par l'utilisateur.")
                    self.log.emit("Opération annulée par l'utilisateur")
                    self.cancelled.emit()
                    return

                doc = DocumentModel.get_by_id(task["doc_id"])
                deck = DeckModel.get_by_id(task["deck_id"])
                note_type = NoteTypeModel.get_by_id(task["model_id"])
                pipeline = PipelineModel.get_by_id(task["pipeline_id"])
                chunk_strategy = task["chunk_strategy"]
                use_vision = task.get("use_vision", False)
                media_dir = get_app_data_dir() / "media"

                steps = list(pipeline.steps.order_by(PipelineStepModel.step_order))

                llm_config = LLMConfigModel.get_by_id(task["llm_id"])
                max_tokens = llm_config.context_limit
                active_provider = AIManager.create_provider_from_config(llm_config)

                fields = json.loads(note_type.fields_schema) if note_type.fields_schema else ["Front", "Back"]
                fields_str = '", "'.join(fields)
                first_field = fields[0] if len(fields) > 0 else "Field1"
                second_field = fields[1] if len(fields) > 1 else "Field2"
                templates = json.loads(note_type.templates) if note_type.templates else []

                optimal_max_chars = min(4000, int((max_tokens * 0.5) * 4))

                logger.info(f"Traitement du document '{doc.title}' ({task_idx + 1}/{total_tasks}).")
                self.progress_text.emit(f"Traitement : {doc.title} ({task_idx + 1}/{total_tasks})...")
                self.log.emit(f"\n{'=' * 40}\n DEBUT : {doc.title}\n⚙ Moteur : {llm_config.display_name} ({max_tokens} tks)\n{'=' * 40}")
                # PARTITIONNEMENT DU DOCUMENT
                chunks = smart_chunk_text(doc.content, strategy=chunk_strategy, max_chars=optimal_max_chars)
                logger.info(f"Document '{doc.title}' découpé en {len(chunks)} morceaux.")
                self.log.emit(f"️ Découpé en {len(chunks)} morceau(x) (Max chars: {optimal_max_chars}).")

                doc_success_notes = 0

                for chunk_idx, chunk_text in enumerate(chunks, 1):
                    if self._is_cancelled:
                        logger.info("Traitement par lots annulé par l'utilisateur pendant le découpage.")
                        self.log.emit("Opération annulée par l'utilisateur")
                        self.cancelled.emit()
                        return

                    self.log.emit(f"\n--- Morceau {chunk_idx}/{len(chunks)} ---")
                    current_input = f"TEXTE SOURCE :\n{chunk_text}"
                    cleaned_output = ""
                    chunk_failed = False

                    for _, step in enumerate(steps, 1):
                        if self._is_cancelled:
                            logger.info("Traitement par lots annulé par l'utilisateur pendant le pipeline.")
                            self.log.emit("Opération annulée par l'utilisateur")
                            self.cancelled.emit()
                            return
                        agent = step.agent
                        logger.info(f"Agent '{agent.name}' en action sur morceau {chunk_idx}/{len(chunks)} de '{doc.title}'.")
                        self.log.emit(f"🤖 Agent '{agent.name}' en action...")

                        jinja_template = Template(agent.system_prompt)
                        system_prompt = jinja_template.render(fields_str=fields_str, first_field=first_field, second_field=second_field)

                        try:
                            if use_vision:
                                payload = prepare_multimodal_payload(current_input, media_dir)
                                raw_response = active_provider.generate(system_prompt=system_prompt, user_prompt=payload)
                            else:
                                clean_input = strip_image_tags(current_input)
                                raw_response = active_provider.generate(system_prompt=system_prompt, user_prompt=clean_input)

                            cleaned_output = self._clean_json(raw_response)
                            current_input = f"Voici les données à traiter :\n{cleaned_output}"
                        except Exception as e:
                            logger.exception(f"Erreur IA sur le morceau {chunk_idx} du document '{doc.title}' :")
                            self.log.emit(f" ERREUR IA sur le morceau {chunk_idx}: {str(e)}")
                            chunk_failed = True
                            break

                    if chunk_failed:
                        continue

                    try:
                        data = json.loads(cleaned_output)
                        notes_to_create = data.get("notes", [])

                        if notes_to_create:
                            with db.atomic():
                                for note_data in notes_to_create:
                                    cleaned_note_data = {}
                                    lower_note_data = {str(k).lower().strip(): v for k, v in note_data.items()}
                                    raw_values = list(note_data.values())

                                    for i, field in enumerate(fields):
                                        field_lower = field.lower().strip()

                                        if field_lower in lower_note_data:
                                            val = lower_note_data[field_lower]
                                        elif i < len(raw_values):
                                            val = raw_values[i]
                                        else:
                                            val = ""

                                        if isinstance(val, list):
                                            val = "<br>".join([str(item) for item in val])
                                        else:
                                            val = str(val) if val is not None else ""

                                        cleaned_note_data[field] = val

                                    note = NoteModel.create(
                                        guid=str(uuid.uuid4())[:10],
                                        note_type=note_type,
                                        tags=json.dumps(["AnkiForge_Batch"]),
                                        status="pending",
                                    )
                                    NoteVersionModel.create(
                                        note=note,
                                        version_number=1,
                                        content=json.dumps(cleaned_note_data, ensure_ascii=False),
                                        # On sauve les données propres
                                        source="ai_batch",
                                        is_active=True,
                                    )
                                    is_cloze = any("{{cloze:" in t.get("qfmt", "") or "{{cloze:" in t.get("afmt", "") for t in templates)

                                    if is_cloze:
                                        max_cloze = get_max_cloze_index(cleaned_note_data)  # Attention à bien utiliser cleaned_note_data ici aussi !
                                        num_cards = max(1, max_cloze)
                                        for i in range(num_cards):
                                            CardModel.create(note=note, deck=deck, template_index=i)
                                    else:
                                        for idx, _ in enumerate(templates):
                                            CardModel.create(note=note, deck=deck, template_index=idx)

                            doc_success_notes += len(notes_to_create)
                            logger.info(f"{len(notes_to_create)} notes créées pour le morceau {chunk_idx} de '{doc.title}'.")
                            self.log.emit(f"✅ {len(notes_to_create)} cartes extraites.")
                    except json.JSONDecodeError:
                        logger.exception(f"Format JSON invalide pour le morceau {chunk_idx} de '{doc.title}'.")
                        self.log.emit("❌ ERREUR JSON : Format invalide.")

                if doc_success_notes > 0:
                    success_count += 1
                    logger.info(f"Bilan '{doc.title}' : {doc_success_notes} cartes générées.")
                    self.log.emit(f"🎉 BILAN : {doc_success_notes} cartes générées au total pour '{doc.title}'.")
                else:
                    error_count += 1
                    logger.warning(f"Échec total pour '{doc.title}'.")
                    self.log.emit(f"❌ ÉCHEC TOTAL : Aucune carte générée pour '{doc.title}'.")

                progress_pct = int(((task_idx + 1) / total_tasks) * 100)
                self.progress_val.emit(progress_pct)

            self.finished.emit(success_count, error_count)

        except Exception as e:
            logger.exception("Erreur fatale lors du traitement par lots :")
            self.error.emit(f"Erreur fatale du BatchWorker : {str(e)}")

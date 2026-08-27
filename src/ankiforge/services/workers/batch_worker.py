import json
import logging
from typing import Any
from dataclasses import dataclass

from PySide6.QtCore import QThread, Signal
from jinja2 import Template

from ankiforge.services.ai.flexible_service import AIManager
from ankiforge.utils.chunker import smart_chunk_text
from ankiforge.utils.paths import get_media_dir
from ankiforge.utils.vision_utils import strip_image_tags, prepare_multimodal_payload

logger = logging.getLogger(__name__)


@dataclass
class BatchTaskPayload:
    """
    Conteneur de données brutes pour une tâche de traitement par lots.
    Évite les accès directs à la base de données dans le thread secondaire.
    """

    doc_id: int
    doc_title: str
    doc_content: str
    deck_id: int
    model_id: int
    note_type_fields: list[str]
    note_type_templates: list[dict[str, Any]]
    pipeline_id: int
    pipeline_steps: list[dict[str, Any]]  # Chaque dict contient 'name', 'system_prompt', 'output_format'
    llm_id: int
    llm_config: dict[str, Any]  # Contient 'display_name', 'model_id', 'context_limit', 'api_key', 'provider'
    chunk_strategy: str
    use_vision: bool


class BatchWorker(QThread):
    """
    Worker massif traitant une file d'attente de documents.

    Gère le découpage intelligent (chunking) et le passage dans les pipelines d'agents.
    Les données extraites sont renvoyées via le signal batch_data_ready pour sauvegarde
    sur le thread principal.
    """

    progress_val = Signal(int)
    progress_text = Signal(str)
    log = Signal(str)
    finished = Signal(int, int)
    error = Signal(str)
    cancelled = Signal()
    # Signal transmettant (liste_de_notes_nettoyées, deck_id, model_id)
    batch_data_ready = Signal(list, int, int)

    def __init__(self, ai_provider: Any, tasks: list[BatchTaskPayload]):
        """
        Initialise le worker de traitement par lots.

        Args:
            ai_provider (Any): Le fournisseur IA par défaut (facultatif car chaque tâche a sa config).
            tasks (list[BatchTaskPayload]): Liste des tâches préparées.
        """
        super().__init__()
        self.ai_provider = ai_provider
        self.tasks = tasks
        self._is_cancelled = False

    def cancel(self) -> None:
        """Demande l'arrêt immédiat de tous les traitements en cours."""
        self._is_cancelled = True

    @staticmethod
    def _clean_json(raw_text: str) -> str:
        """
        Nettoie le texte brut pour en extraire le JSON (supprime les balises markdown).

        Args:
            raw_text (str): Texte brut généré par l'IA.

        Returns:
            str: JSON nettoyé.
        """
        clean = raw_text.strip()
        if clean.startswith("```json"):
            clean = clean[7:-3].strip()
        elif clean.startswith("```"):
            clean = clean[3:-3].strip()
        return clean

    def run(self) -> None:
        """Exécute séquentiellement chaque tâche de la liste."""
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

                # Données extraites de la dataclass (PAS DE PEEWEE ICI)
                doc_title = task.doc_title
                doc_content = task.doc_content
                chunk_strategy = task.chunk_strategy
                use_vision = task.use_vision
                media_dir = get_media_dir()

                llm_cfg = task.llm_config
                max_tokens = llm_cfg["context_limit"]

                # Instanciation thread-safe du provider
                active_provider = AIManager.create_provider(provider_name=llm_cfg["provider"], model_id=llm_cfg["model_id"], api_key=llm_cfg["api_key"])

                fields = task.note_type_fields
                fields_str = '", "'.join(fields)
                first_field = fields[0] if len(fields) > 0 else "Field1"
                second_field = fields[1] if len(fields) > 1 else "Field2"

                optimal_max_chars = min(4000, int((max_tokens * 0.5) * 4))

                logger.info(f"Traitement du document '{doc_title}' ({task_idx + 1}/{total_tasks}).")
                self.progress_text.emit(f"Traitement : {doc_title} ({task_idx + 1}/{total_tasks})...")
                self.log.emit(f"\n{'=' * 40}\n DEBUT : {doc_title}\n⚙ Moteur : {llm_cfg['display_name']} ({max_tokens} tks)\n{'=' * 40}")

                # PARTITIONNEMENT DU DOCUMENT
                chunks = smart_chunk_text(doc_content, strategy=chunk_strategy, max_chars=optimal_max_chars)
                logger.info(f"Document '{doc_title}' découpé en {len(chunks)} morceaux.")
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

                    for _, agent_data in enumerate(task.pipeline_steps, 1):
                        if self._is_cancelled:
                            logger.info("Traitement par lots annulé par l'utilisateur pendant le pipeline.")
                            self.log.emit("Opération annulée par l'utilisateur")
                            self.cancelled.emit()
                            return

                        agent_name = agent_data["name"]
                        agent_system_prompt = agent_data["system_prompt"]
                        output_format = agent_data.get("output_format", "json")

                        logger.info(f"Agent '{agent_name}' en action sur morceau {chunk_idx}/{len(chunks)} de '{doc_title}'.")
                        self.log.emit(f"🤖 Agent '{agent_name}' en action...")

                        jinja_template = Template(agent_system_prompt)
                        system_prompt = jinja_template.render(fields_str=fields_str, first_field=first_field, second_field=second_field)

                        try:
                            if use_vision:
                                payload = prepare_multimodal_payload(current_input, media_dir)
                                raw_response = active_provider.generate(system_prompt=system_prompt, user_prompt=payload, response_format=output_format)
                            else:
                                clean_input = strip_image_tags(current_input)
                                raw_response = active_provider.generate(system_prompt=system_prompt, user_prompt=clean_input, response_format=output_format)

                            cleaned_output = self._clean_json(raw_response)
                            current_input = f"Voici les données à traiter :\n{cleaned_output}"
                        except Exception as e:
                            logger.exception(f"Erreur IA sur le morceau {chunk_idx} du document '{doc_title}' :")
                            self.log.emit(f" ERREUR IA sur le morceau {chunk_idx}: {str(e)}")
                            chunk_failed = True
                            break

                    if chunk_failed:
                        continue

                    try:
                        data = json.loads(cleaned_output)
                        notes_to_process = data.get("notes", [])

                        if notes_to_process:
                            prepared_chunk_data = []
                            for note_data in notes_to_process:
                                cleaned_note_fields = {}
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

                                    cleaned_note_fields[field] = val

                                prepared_chunk_data.append(cleaned_note_fields)

                            # On envoie les données au thread principal pour sauvegarde
                            self.batch_data_ready.emit(prepared_chunk_data, task.deck_id, task.model_id)

                            doc_success_notes += len(notes_to_process)
                            logger.info(f"{len(notes_to_process)} notes préparées pour le morceau {chunk_idx} de '{doc_title}'.")
                            self.log.emit(f"✅ {len(notes_to_process)} cartes extraites.")
                    except json.JSONDecodeError:
                        logger.exception(f"Format JSON invalide pour le morceau {chunk_idx} de '{doc_title}'.")
                        self.log.emit("❌ ERREUR JSON : Format invalide.")

                if doc_success_notes > 0:
                    success_count += 1
                    logger.info(f"Bilan '{doc_title}' : {doc_success_notes} cartes générées.")
                    self.log.emit(f"🎉 BILAN : {doc_success_notes} cartes générées au total pour '{doc_title}'.")
                else:
                    error_count += 1
                    logger.warning(f"Échec total pour '{doc_title}'.")
                    self.log.emit(f"❌ ÉCHEC TOTAL : Aucune carte générée pour '{doc_title}'.")

                progress_pct = int(((task_idx + 1) / total_tasks) * 100)
                self.progress_val.emit(progress_pct)

            self.finished.emit(success_count, error_count)

        except Exception as e:
            logger.exception("Erreur fatale lors du traitement par lots :")
            self.error.emit(f"Erreur fatale du BatchWorker : {str(e)}")

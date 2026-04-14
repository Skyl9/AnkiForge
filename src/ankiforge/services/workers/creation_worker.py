import json
import logging
from typing import Any

from PySide6.QtCore import QThread, Signal

from ankiforge.database.models import PipelineModel, NoteTypeModel, PipelineStepModel
from ankiforge.services.ai.utils import parse_ai_json_response, format_system_prompt
from ankiforge.utils.paths import get_app_data_dir
from ankiforge.utils.vision_utils import prepare_multimodal_payload, strip_image_tags

logger = logging.getLogger(__name__)


class CreationWorker(QThread):
    """
    Thread asynchrone responsable de l'exécution du pipeline de génération.
    Il orchestre l'extraction, la transformation et le formatage du texte source via les LLMs.
    """

    finished = Signal(list)
    error = Signal(str)
    progress = Signal(str)
    log = Signal(str)
    cancelled = Signal()

    def __init__(self, ai_provider: Any, text_source: str, note_type_id: int, pipeline_id: int, use_vision: bool) -> None:
        """
        Initialise le thread de génération.

        Args:
            ai_provider (LLMProvider): Le moteur IA à utiliser pour l'inférence.
            text_source (str): Le texte brut à analyser.
            note_type_id (int): L'identifiant du modèle Anki cible.
            pipeline_id (int): L'identifiant de la chaîne d'exécution (agents).
            use_vision (bool): Active l'extraction et l'envoi des images jointes au texte.
        """
        super().__init__()
        self.ai_provider = ai_provider
        self.text_source = text_source
        self.note_type_id = note_type_id
        self.pipeline_id = pipeline_id
        self.use_vision = use_vision
        self._is_cancelled = False

    def cancel(self) -> None:
        """Lève le drapeau d'annulation pour interrompre le traitement."""
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
        cleaned_output = ""
        raw_response = ""
        try:
            pipeline = PipelineModel.get_by_id(self.pipeline_id)
            note_type = NoteTypeModel.get_by_id(self.note_type_id)

            steps = list(pipeline.steps.order_by(PipelineStepModel.step_order))

            if not steps:
                raise ValueError(f"Le pipeline '{pipeline.name}' ne contient aucun agent !")
            fields = json.loads(note_type.fields_schema) if note_type.fields_schema else ["Front", "Back"]

            current_input = f"TEXTE SOURCE :\n{self.text_source}"
            total_steps = len(steps)

            for i, step in enumerate(steps, 1):
                if self._is_cancelled:
                    logger.info("Génération annulée par l'utilisateur pendant le pipeline.")
                    self.log.emit("\n Génération annulée par l'utilisateur.")
                    self.cancelled.emit()
                    return
                agent = step.agent
                output_format = getattr(agent, "output_format", "json")
                self.progress.emit(f"Étape {i}/{total_steps} : {agent.name}...")

                system_prompt = format_system_prompt(agent.system_prompt, note_type.fields_schema)

                logger.info(f"Début étape {i}/{total_steps} : Agent '{agent.name}'")
                self.log.emit(f"--- DÉBUT ÉTAPE {i} : {agent.name.upper()} ---\n")
                self.log.emit(f"PROMPT SYSTÈME :\n{system_prompt}\n")
                self.log.emit(f"ENTRÉE UTILISATEUR :\n{current_input}\n")

                if self.use_vision:
                    media_dir = get_app_data_dir() / "media"
                    payload = prepare_multimodal_payload(current_input, media_dir)
                    raw_response = self.ai_provider.generate(system_prompt=system_prompt, user_prompt=payload, response_format=output_format)
                else:
                    clean_input = strip_image_tags(current_input)
                    raw_response = self.ai_provider.generate(system_prompt=system_prompt, user_prompt=clean_input, response_format=output_format)

                logger.debug(f"Réponse brute de l'IA pour l'étape {i} : {raw_response[:100]}...")
                self.log.emit(f"RÉPONSE BRUTE DE L'IA :\n{raw_response}\n\n")

                cleaned_output = self._clean_json(raw_response)
                current_input = f"Voici les données à traiter (provenant de l'étape précédente) :\n{cleaned_output}"

            data = parse_ai_json_response(raw_response)

            if "notes" not in data:
                raise ValueError("Le JSON final ne contient pas la clé 'notes'.")

            raw_notes = data["notes"]
            cleaned_notes_to_create = []

            # Validation stricte des clés JSON et fallback séquentiel
            for note_data in raw_notes:
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

                cleaned_notes_to_create.append(cleaned_note_data)

            self.finished.emit(cleaned_notes_to_create)

        except json.JSONDecodeError as e:
            logger.exception("Erreur de décodage JSON lors de la génération :")
            self.error.emit(f"L'un des agents a brisé le format JSON.\nErreur : {e}\n\nDernière sortie:\n{cleaned_output[:200]}")
        except Exception as e:
            logger.exception("Erreur critique lors du pipeline de génération :")
            self.error.emit(f"Erreur lors du pipeline IA : {str(e)}")

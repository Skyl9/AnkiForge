import json
import logging
from typing import Any
from dataclasses import dataclass

from PySide6.QtCore import QThread, Signal

from ankiforge.services.ai.utils import AIReponseParser, format_system_prompt
from ankiforge.utils.paths import get_app_data_dir
from ankiforge.utils.vision_utils import prepare_multimodal_payload, strip_image_tags

logger = logging.getLogger(__name__)


@dataclass
class CreationTaskPayload:
    """
    Conteneur de données brutes pour une tâche de génération unique.
    Évite les accès directs à la base de données dans le thread secondaire.
    """

    text_source: str
    note_type_id: int
    note_type_fields_schema: str
    pipeline_id: int
    pipeline_name: str
    pipeline_steps: list[dict[str, Any]]  # Chaque dict contient 'name', 'system_prompt', 'output_format'
    use_vision: bool


class CreationWorker(QThread):
    """
    Moteur asynchrone de génération de flashcards.

    Gère le passage successif du texte source à travers une chaîne d'agents IA (pipeline).
    Supporte la vision, le nettoyage de JSON et le reformatage des champs selon le modèle Anki.
    """

    finished = Signal(list)
    error = Signal(str)
    progress = Signal(str)
    log = Signal(str)
    cancelled = Signal()

    def __init__(self, ai_provider: Any, payload: CreationTaskPayload) -> None:
        """
        Initialise le worker de génération unique.

        Args:
            ai_provider (Any): Le fournisseur IA actif.
            payload (CreationTaskPayload): Les données préparées de la tâche.
        """
        super().__init__()
        self.ai_provider = ai_provider
        self.payload = payload
        self._is_cancelled = False

    def cancel(self) -> None:
        """Demande l'arrêt de la génération en cours."""
        self._is_cancelled = True

    @staticmethod
    def _clean_json(raw_text: str) -> str:
        """
        Nettoie le texte pour isoler le JSON (supprime les blocs markdown).

        Args:
            raw_text (str): Texte brut de l'IA.

        Returns:
            str: JSON prêt pour le parsing.
        """
        clean = raw_text.strip()
        if clean.startswith("```json"):
            clean = clean[7:-3].strip()
        elif clean.startswith("```"):
            clean = clean[3:-3].strip()
        return clean

    def run(self) -> None:
        """Exécute les étapes du pipeline et émet la liste des notes générées."""
        cleaned_output = ""
        raw_response = ""
        try:
            steps = self.payload.pipeline_steps

            if not steps:
                raise ValueError(f"Le pipeline '{self.payload.pipeline_name}' ne contient aucun agent !")

            fields = json.loads(self.payload.note_type_fields_schema) if self.payload.note_type_fields_schema else ["Front", "Back"]

            current_input = f"TEXTE SOURCE :\n{self.payload.text_source}"
            total_steps = len(steps)

            for i, step_data in enumerate(steps, 1):
                if self._is_cancelled:
                    logger.info("Génération annulée par l'utilisateur pendant le pipeline.")
                    self.log.emit("\n Génération annulée par l'utilisateur.")
                    self.cancelled.emit()
                    return

                agent_name = step_data["name"]
                agent_system_prompt = step_data["system_prompt"]
                output_format = step_data.get("output_format", "json")

                self.progress.emit(f"Étape {i}/{total_steps} : {agent_name}...")

                system_prompt = format_system_prompt(agent_system_prompt, self.payload.note_type_fields_schema)

                logger.info(f"Début étape {i}/{total_steps} : Agent '{agent_name}'")
                self.log.emit(f"--- DÉBUT ÉTAPE {i} : {agent_name.upper()} ---\n")
                self.log.emit(f"PROMPT SYSTÈME :\n{system_prompt}\n")
                self.log.emit(f"ENTRÉE UTILISATEUR :\n{current_input}\n")

                if self.payload.use_vision:
                    media_dir = get_app_data_dir() / "media"
                    payload_multimodal = prepare_multimodal_payload(current_input, media_dir)
                    raw_response = self.ai_provider.generate(system_prompt=system_prompt, user_prompt=payload_multimodal, response_format=output_format)
                else:
                    clean_input = strip_image_tags(current_input)
                    raw_response = self.ai_provider.generate(system_prompt=system_prompt, user_prompt=clean_input, response_format=output_format)

                logger.debug(f"Réponse brute de l'IA pour l'étape {i} : {raw_response[:100]}...")
                self.log.emit(f"RÉPONSE BRUTE DE L'IA :\n{raw_response}\n\n")

                cleaned_output = self._clean_json(raw_response)
                current_input = f"Voici les données à traiter (provenant de l'étape précédente) :\n{cleaned_output}"

            data = AIReponseParser.parse(raw_response)

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

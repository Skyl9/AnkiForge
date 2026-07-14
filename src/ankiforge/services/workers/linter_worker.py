import json
import logging
import dataclasses

from PySide6.QtCore import QThread, Signal

from ankiforge.database.models import NoteModel, NoteVersionModel
from ankiforge.services.ai.flexible_service import AIManager
from ankiforge.services.ai.utils import AIReponseParser

logger = logging.getLogger(__name__)

# The 20 rules of formulating knowledge prompt (Wozniak)
LINTER_SYSTEM_PROMPT = """You are an expert Anki flashcard auditor following Piotr Wozniak's '20 rules of formulating knowledge'.
Your goal is to review the provided flashcards and point out major violations of the rules (e.g., lack of atomicity, complex lists, redundancy, poorly formulated questions, lack of context).

For each note, output whether it passes or fails, the rule broken, and a suggested improvement. 
Return a JSON array of objects.

JSON Structure:
[
  {
    "note_id": 123,
    "pass": false,
    "rule_broken": "Atomicity",
    "reason": "The card asks for 3 different concepts at once.",
    "suggestion": {"Front": "Question 1?", "Back": "Answer 1"} 
  }
]
Always wrap your response in standard JSON. Only provide suggestions if it fails.
"""


@dataclasses.dataclass
class LinterResult:
    note_id: int
    pass_: bool
    rule_broken: str | None = None
    reason: str | None = None
    suggestion: dict | None = None


class LinterWorker(QThread):
    finished_processing = Signal(list)  # List of dicts or LinterResult
    error_occurred = Signal(str)
    progress_update = Signal(str)

    def __init__(self, note_ids: list[int]):
        super().__init__()
        self.note_ids = note_ids
        # Flexible AIManager initialization (uses active config in DB)
        self.ai_manager = AIManager()

    def run(self):
        try:
            self.progress_update.emit("Initialisation de l'agent linter...")
            llm_provider = self.ai_manager.provider

            # Retrieve notes
            notes_data = []
            for nid in self.note_ids:
                note = NoteModel.get_by_id(nid)
                active_version = NoteVersionModel.get_or_none(note=note, is_active=True)
                if active_version:
                    notes_data.append({"note_id": note.id, "content": json.loads(active_version.content)})

            if not notes_data:
                self.finished_processing.emit([])
                return

            self.progress_update.emit(f"Audit de {len(notes_data)} cartes en cours...")

            user_prompt = f"Voici les cartes à auditer :\n{json.dumps(notes_data, ensure_ascii=False)}"

            # Using JSON response format
            raw_response = llm_provider.generate(system_prompt=LINTER_SYSTEM_PROMPT, user_prompt=user_prompt, response_format="json")

            # Parse using the new AIReponseParser
            results = AIReponseParser.parse(raw_response)

            # In case the IA used "pass" instead of "pass_" in dict
            # We will just pass the dict list down to the UI
            if not isinstance(results, list):
                raise ValueError("L'IA n'a pas renvoyé une liste JSON.")

            self.finished_processing.emit(results)

        except Exception as e:
            logger.error(f"Linter error: {e}", exc_info=True)
            self.error_occurred.emit(str(e))

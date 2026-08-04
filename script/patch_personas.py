import sys
from pathlib import Path

# Override the DEFAULT_DB_PATH before importing models
import ankiforge.database.models
ankiforge.database.models.DEFAULT_DB_PATH = Path("/Users/tristanrigaud-humbert/PycharmProjects/AnkiForge/.ankiforge/ankiforge.db")

from ankiforge.database.models import db, PersonaModel

wozniak_prompt = (
    "You are an expert Anki flashcard auditor following Piotr Wozniak's '20 rules of formulating knowledge'.\n"
    "Your goal is to review the provided flashcards and point out major violations of the rules (e.g., lack of atomicity, complex lists, redundancy, poorly formulated questions, lack of context).\n\n"
    "For each note, output whether it passes or fails, the rule broken, and a suggested improvement. \n"
    "Return a JSON array of objects.\n\n"
    "JSON Structure:\n"
    "[\n"
    "  {\n"
    "    \"note_id\": 123,\n"
    "    \"pass\": false,\n"
    "    \"rule_broken\": \"Atomicity\",\n"
    "    \"reason\": \"The card asks for 3 different concepts at once.\",\n"
    "    \"suggestion\": {\"Front\": \"Question 1?\", \"Back\": \"Answer 1\"} \n"
    "  }\n"
    "]\n"
    "Always wrap your response in standard JSON. Only provide suggestions if it fails."
)

db.init(ankiforge.database.models.DEFAULT_DB_PATH)
db.connect(reuse_if_open=True)

persona, created = PersonaModel.get_or_create(
    name="Auditeur Wozniak",
    defaults={"description": "Auditeur expert basé sur les 20 règles de formulation de Piotr Wozniak.", "system_prompt": wozniak_prompt},
)
if created:
    print("Auditeur Wozniak ADDED successfully!")
else:
    print("Auditeur Wozniak was ALREADY THERE.")

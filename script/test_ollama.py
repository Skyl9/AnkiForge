from ankiforge.database.models import db, LLMConfigModel
from ankiforge.services.ai.flexible_service import AIManager, OllamaProvider
from ankiforge.services.workers.creation_worker import CreationWorker, CreationTaskPayload
from PySide6.QtWidgets import QApplication
import sys

app = QApplication(sys.argv)
db.connect(reuse_if_open=True)

provider = OllamaProvider("qwen2.5:7b")

payload = CreationTaskPayload(
    text_source="Le soleil est une étoile jaune naine.",
    note_type_id=1,
    note_type_fields_schema='["Front", "Back"]',
    pipeline_id=None,
    pipeline_name="Custom",
    pipeline_steps=[{"name": "tests", "system_prompt": "Crée une carte Anki avec les champs Front et Back. Renvoie un JSON valide au format {'notes': [{'Front': '...', 'Back': '...'}]}.", "output_format": "json"}],
    use_vision=False
)

worker = CreationWorker(provider, payload)
worker.log.connect(lambda msg: print(f"LOG: {msg}"))
worker.error.connect(lambda err: print(f"ERROR: {err}"))
worker.finished.connect(lambda res: print(f"FINISHED: {res}"))

worker.run()

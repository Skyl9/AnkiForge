from ankiforge.database.models import db, LLMConfigModel
from ankiforge.services.ai.flexible_service import AIManager
from ankiforge.services.workers.creation_worker import CreationWorker, CreationTaskPayload
from PySide6.QtWidgets import QApplication
import sys

app = QApplication(sys.argv)
db.connect(reuse_if_open=True)

manager = AIManager()
gemini_config = LLMConfigModel.get_or_none(LLMConfigModel.model_id == "gemini-2.5-flash")
if not gemini_config: gemini_config = LLMConfigModel.select().first()

provider = manager.create_provider_from_config(gemini_config)

payload = CreationTaskPayload(
    text_source="Le soleil est une étoile jaune naine.",
    note_type_id=1,
    note_type_fields_schema='["Front", "Back"]',
    pipeline_id=None,
    pipeline_name="Custom",
    pipeline_steps=[{"name": "tests", "system_prompt": "Fais un JSON avec notes: [{Front, Back}]", "output_format": "json"}],
    use_vision=False
)

worker = CreationWorker(provider, payload)
worker.log.connect(lambda msg: print(f"LOG: {msg}"))
worker.error.connect(lambda err: print(f"ERROR: {err}"))
worker.finished.connect(lambda res: print(f"FINISHED: {res}"))

worker.run()

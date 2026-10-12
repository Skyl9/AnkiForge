from __future__ import annotations

import json

import pytest
from PIL import Image

from ankiforge.database.models import (
    DeckModel,
    DocumentChunkModel,
    DocumentModel,
    DocumentPageModel,
    MediaModel,
    NoteTypeModel,
    PersonaModel,
    PipelineModel,
    PipelineStepModel,
)
from ankiforge.services.ai.base import LLMResult, MockProvider
from ankiforge.services.batch.models import (
    BatchGenerationConfig,
    BatchScopeSnapshot,
    BatchSourceBlock,
    BatchTaskSnapshot,
)
from ankiforge.services.workers.batch_worker import BatchWorker

pytestmark = pytest.mark.unit


class MultimodalCapturingProvider(MockProvider):
    def __init__(self) -> None:
        super().__init__()
        self.captured_payloads: list[list[dict]] = []

    def generate_response(self, system_prompt: str, user_prompt: str | list[dict], **kwargs) -> LLMResult:
        if isinstance(user_prompt, list):
            self.captured_payloads.append(user_prompt)
        return LLMResult(
            content=json.dumps({"notes": [{"Front": "Q_Plate", "Back": "A_Plate"}]}),
            raw_response="ok",
        )


@pytest.fixture
def album_batch_fixture(tmp_path, monkeypatch):
    media_dir = tmp_path / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("ankiforge.utils.paths.get_media_dir", lambda *args, **kwargs: media_dir)

    img1_path = media_dir / "plate_batch_p1.png"
    img1 = Image.new("RGB", (100, 100), color="green")
    img1.save(img1_path)

    doc = DocumentModel.create(
        title="Atlas Batch",
        file_type="album",
        total_pages=1,
        content="",
    )
    m = MediaModel.create(
        filename="plate_batch_p1.png",
        media_type="image",
        original_name="plate_batch_p1.png",
        checksum="chk_batch",
        mime_type="image/png",
    )
    page = DocumentPageModel.create(
        document=doc,
        media=m,
        page_number=1,
        rotation=0,
        ocr_text="Anatomie fémorale et artérielle.",
        status="ready",
    )
    chunk = DocumentChunkModel.create(
        document=doc,
        page_number=1,
        chunk_index=0,
        content="<!-- PAGE: 1 -->\nAnatomie fémorale et artérielle.",
        media=m,
    )
    deck = DeckModel.create(name="Default")
    nt = NoteTypeModel.create(name="Basique", fields_schema=json.dumps(["Front", "Back"]), templates="[]", css_style="")
    pipe = PipelineModel.create(name="Standard")
    persona = PersonaModel.create(name="Extractor", system_prompt="Extrais.", output_format="json")
    PipelineStepModel.create(pipeline=pipe, persona=persona, step_order=1)

    return doc, page, chunk, deck, nt, pipe, media_dir


def test_batch_worker_snapshot_task_album_vision(album_batch_fixture):
    """Vérifie qu'en mode Batch, une tâche d'album avec use_vision=True inclut bien l'image de la planche."""
    doc, page, chunk, deck, nt, pipe, media_dir = album_batch_fixture
    provider = MultimodalCapturingProvider()

    block = BatchSourceBlock(
        kind="page",
        label="Page 1",
        content="Anatomie fémorale et artérielle.",
        ordinal=1,
        page_number=1,
        chunk_id=chunk.id,
    )
    scope = BatchScopeSnapshot(
        document_id=doc.id,
        document_title=doc.title,
        selection_mode="pages",
        blocks=(block,),
        scope_title="Page 1",
    )
    config = BatchGenerationConfig(
        pipeline_id=pipe.id,
        pipeline_name=pipe.name,
        llm_id=1,
        llm_config={"provider": "mock", "model_id": "test"},
        deck_id=deck.id,
        deck_name=deck.name,
        model_id=nt.id,
        model_name=nt.name,
        note_type_fields=("Front", "Back"),
        use_vision=True,
    )
    task = BatchTaskSnapshot(task_id="t1", scope=scope, config=config, task_index=0)

    worker = BatchWorker(ai_provider=provider, tasks=[task])
    worker.run()

    assert len(provider.captured_payloads) == 1, "Le provider aurait dû recevoir un payload multimodal"
    payload = provider.captured_payloads[0]
    img_parts = [p for p in payload if p.get("type") == "image_url"]
    assert len(img_parts) == 1, "L'image de la planche d'album aurait dû être attachée au payload batch"
    assert "data:image/png;base64," in img_parts[0]["image_url"]["url"]

import json
from typing import Any

import pytest
from PySide6.QtCore import Qt

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    DocumentChunkModel,
    DocumentModel,
    LLMConfigModel,
    NoteChunkLinkModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionModel,
    PipelineModel,
    PipelineStepModel,
)
from ankiforge.services.ai.orchestrator import PipelineOrchestrator
from ankiforge.services.batch.models import BatchTaskSnapshot
from ankiforge.services.workers.batch_worker import BatchTaskPayload, BatchWorker
from ankiforge.ui.views.batch_view import BatchTab

pytestmark = pytest.mark.ui


def test_batch_views_creation(qtbot: Any) -> None:
    """Vérifie l'instanciation de base de BatchTab."""
    view = BatchTab(ai_manager=None)
    qtbot.addWidget(view)
    assert view is not None
    assert view.queue_table.columnCount() == 9


def test_batch_view_initialization_with_data(qtbot: Any) -> None:
    """Vérifie le chargement des documents, paquets, modèles et pipelines dans l'UI."""
    # Création des données de test
    DeckModel.create(name="Deck Test Batch")
    NoteTypeModel.create(name="Basic Test Batch", fields_schema='["Front", "Back"]', templates="[]", css_style="")
    pipe = PipelineModel.create(name="Pipeline Test Batch")
    PipelineStepModel.create(pipeline=pipe, step_type="LLM_PROMPT", step_order=1, config_data=json.dumps({"prompt_template": "Test"}))
    LLMConfigModel.create(display_name="LLM Test", provider="openai", model_id="gpt-4o-mini", api_key="sk-test")
    DocumentModel.create(title="Cours IA.pdf", content_markdown="Contenu cours IA", file_type="pdf")
    DocumentModel.create(title="Histoire.md", content_markdown="Contenu histoire", file_type="md")

    view = BatchTab(ai_manager=None)
    qtbot.addWidget(view)

    # Vérification de la présence du composeur fusionné (remplace liste + inspecteur legacy)
    assert hasattr(view, "btn_compose_batch")
    assert "Composer le lot" in view.btn_compose_batch.text()

    # Vérification des sélecteurs de Deck et Modèle
    assert view.btn_select_deck.text() != ""
    assert view.btn_select_model.text() != ""

    # Vérification du sélecteur de Pipeline
    pipe_names = [view.pipeline_combo.itemText(i) for i in range(view.pipeline_combo.count())]
    assert any(pipe.name in name for name in pipe_names)

    # Vérification du sélecteur de Moteur IA
    engine_names = [view.engine_combo.itemText(i) for i in range(view.engine_combo.count())]
    assert any("gpt-4o-mini" in name or "LLM Test" in name for name in engine_names)


def test_batch_view_composer_accepts_tasks_and_memorizes_doc(qtbot: Any, monkeypatch: Any, mock_db: Any) -> None:
    """L'ouverture du composeur (bouton unique) ajoute les tâches à la file et mémorise le document."""
    from ankiforge.ui.views.batch_view.dialogs.batch_slice_composer_dialog import BatchSliceComposerDialog

    doc = DocumentModel.create(title="Doc Composé.pdf", content="Contenu source", file_type="pdf")

    class FakeComposer:
        def exec(self) -> int:
            return 1

        def get_result(self) -> dict[str, Any]:
            return {
                "tasks": [{"doc": doc, "doc_title": doc.title, "doc_content": "Contenu source", "chunk_label": "Chunk 1"}],
                "scope_result": {"chunks": [], "selection_mode": "sections"},
                "doc": doc,
            }

    monkeypatch.setattr(BatchSliceComposerDialog, "exec", FakeComposer.exec)
    monkeypatch.setattr(BatchSliceComposerDialog, "get_result", FakeComposer.get_result)

    view = BatchTab(ai_manager=None)
    qtbot.addWidget(view)
    view.btn_compose_batch.click()

    assert len(view.queue_tasks_data) == 1
    assert view.queue_tasks_data[0]["chunk_label"] == "Chunk 1"
    assert view._last_composer_doc.id == doc.id


def test_batch_view_queue_management(qtbot: Any) -> None:
    """Vérifie l'ajout (via la composition), la suppression unitaire et le vidage de la file d'attente."""
    doc = DocumentModel.create(title="Document File Test.pdf", content_markdown="File test", file_type="pdf")

    view = BatchTab(ai_manager=None)
    qtbot.addWidget(view)

    # Ajouter via la fabrication de tâche Direct (1 partie = 1 tâche)
    task = view._chunk_to_queue_task(doc, {"content": "File test", "title": "Section 1", "index": 0})
    assert task is not None
    view._append_queue_tasks([task])
    assert len(view.queue_tasks_data) >= 1
    assert view.queue_table.rowCount() >= 1

    initial_count = len(view.queue_tasks_data)

    # Supprimer la première tâche
    view._remove_from_queue(0)
    assert len(view.queue_tasks_data) == initial_count - 1

    # Ajouter à nouveau puis vider toute la file
    view._append_queue_tasks([view._chunk_to_queue_task(doc, {"content": "File test", "title": "Section 1", "index": 0})])
    assert len(view.queue_tasks_data) >= 1

    view._on_clear_queue()
    assert len(view.queue_tasks_data) == 0
    assert view.queue_table.rowCount() == 0


def test_batch_worker_run_success(qtbot: Any, monkeypatch: Any) -> None:
    """Vérifie l'exécution du BatchWorker et la création correcte des cartes en base de données."""
    deck = DeckModel.create(name="Deck Worker Test")
    nt = NoteTypeModel.create(
        name="Basic Worker Test",
        fields_schema='["Front", "Back"]',
        templates=json.dumps([{"name": "Card 1", "qfmt": "{{Front}}", "afmt": "{{Back}}"}]),
        css_style="",
    )
    doc = DocumentModel.create(title="Doc Worker Source.md", content_markdown="Source data", file_type="md")
    chunk = DocumentChunkModel.create(document=doc, chunk_index=0, content="Source data chunk")

    task = BatchTaskPayload(
        task_index=0,
        doc_id=doc.id,
        doc_title=doc.title,
        doc_content="Source data",
        deck_id=deck.id,
        deck_name=deck.name,
        model_id=nt.id,
        model_name=nt.name,
        note_type_fields=["Front", "Back"],
        note_type_templates=[{"name": "Card 1", "qfmt": "{{Front}}", "afmt": "{{Back}}"}],
        pipeline_id=1,
        pipeline_name="Standard",
        llm_id=1,
        llm_config={"provider": "mock", "model_id": "mock-model", "api_key": ""},
    )

    worker = BatchWorker(tasks=[task])

    # Simuler le résultat de l'orchestrateur
    def fake_orchestrator_run(self_orch: Any) -> None:
        self_orch.state.variables["generated_cards"] = [
            {"Front": "Quelle est la capitale ?", "Back": "Paris"},
            {"Front": "Combien font 2+2 ?", "Back": "4"},
        ]

    monkeypatch.setattr(PipelineOrchestrator, "run", fake_orchestrator_run)

    completed_payloads = []
    worker.task_completed.connect(lambda idx, notes, count: completed_payloads.append((idx, notes, count)))

    with qtbot.waitSignal(worker.batch_finished, timeout=5000) as blocker:
        worker.start()

    success_count, fail_count, total_cards = blocker.args
    assert success_count == 1
    assert fail_count == 0
    assert total_cards == 2
    assert len(completed_payloads) == 1
    assert len(completed_payloads[0][1]) == 2

    # Vérification de la persistance en BDD via _save_extracted_notes_to_db
    view = BatchTab(ai_manager=None)
    qtbot.addWidget(view)
    view._save_extracted_notes_to_db(completed_payloads[0][1], deck.id, nt.id, doc.id)

    # Plus aucun lien de chunks RAG créé à la forge (pris en charge par la synchronisation par tags)
    links = list(NoteChunkLinkModel.select().where(NoteChunkLinkModel.chunk == chunk))
    assert len(links) == 0

    # Vérification des cartes enfants et de l'historique Time Machine
    saved_notes = list(NoteModel.select())
    assert len(saved_notes) == 2
    for note in saved_notes:
        cards = list(CardModel.select().where(CardModel.note == note))
        assert len(cards) == 1
        # Vérification de l'historique Time Machine
        versions = list(NoteVersionModel.select().where(NoteVersionModel.note == note))
        assert len(versions) == 1


def test_batch_worker_error_resilience(qtbot: Any, monkeypatch: Any) -> None:
    """Vérifie qu'un échec sur une tâche n'interrompt pas le reste du lot."""
    deck = DeckModel.create(name="Deck Resilience")
    nt = NoteTypeModel.create(name="Model Resilience", fields_schema='["Front", "Back"]', templates="[]", css_style="")
    doc1 = DocumentModel.create(title="Doc Fail.md", content_markdown="Fail content", file_type="md")
    doc2 = DocumentModel.create(title="Doc Success.md", content_markdown="Success content", file_type="md")

    task1 = BatchTaskPayload(
        task_index=0,
        doc_id=doc1.id,
        doc_title=doc1.title,
        doc_content="Fail content",
        deck_id=deck.id,
        deck_name=deck.name,
        model_id=nt.id,
        model_name=nt.name,
        note_type_fields=["Front", "Back"],
        note_type_templates=[],
        pipeline_id=1,
        pipeline_name="Standard",
        llm_id=1,
        llm_config={"provider": "mock", "model_id": "mock-model", "api_key": ""},
    )
    task2 = BatchTaskPayload(
        task_index=1,
        doc_id=doc2.id,
        doc_title=doc2.title,
        doc_content="Success content",
        deck_id=deck.id,
        deck_name=deck.name,
        model_id=nt.id,
        model_name=nt.name,
        note_type_fields=["Front", "Back"],
        note_type_templates=[],
        pipeline_id=1,
        pipeline_name="Standard",
        llm_id=1,
        llm_config={"provider": "mock", "model_id": "mock-model", "api_key": ""},
    )

    worker = BatchWorker(tasks=[task1, task2])

    call_count = [0]

    def fake_orchestrator_run_err(self_orch: Any) -> None:
        call_count[0] += 1
        if call_count[0] == 1:
            raise RuntimeError("Simulation d'échec API ou parse error")
        else:
            self_orch.state.variables["generated_cards"] = [{"Front": "Q2", "Back": "A2"}]

    monkeypatch.setattr(PipelineOrchestrator, "run", fake_orchestrator_run_err)

    failed_tasks = []
    worker.task_failed.connect(lambda idx, err: failed_tasks.append((idx, err)))

    with qtbot.waitSignal(worker.batch_finished, timeout=5000) as blocker:
        worker.start()

    success_count, fail_count, total_cards = blocker.args
    assert success_count == 1
    assert fail_count == 1
    assert total_cards == 1
    assert len(failed_tasks) == 1
    assert failed_tasks[0][0] == 0


def test_batch_worker_processes_document_chunks_sequentially(qtbot: Any, monkeypatch: Any) -> None:
    """Le mode document complet isole chaque chunk et conserve leur ordre."""
    seen_sources: list[str] = []
    deck = DeckModel.create(name="Deck Chunked Batch")
    nt = NoteTypeModel.create(name="Model Chunked Batch", fields_schema='["Front", "Back"]', templates="[]", css_style="")
    doc = DocumentModel.create(title="Document Chunked.md", content_markdown="ignored", file_type="md")

    task = BatchTaskPayload(
        task_index=0,
        doc_id=doc.id,
        doc_title=doc.title,
        doc_content="fallback",
        deck_id=deck.id,
        deck_name=deck.name,
        model_id=nt.id,
        model_name=nt.name,
        note_type_fields=["Front", "Back"],
        note_type_templates=[],
        pipeline_id=1,
        pipeline_name="Standard",
        llm_id=1,
        llm_config={"provider": "mock", "model_id": "mock-model", "api_key": ""},
        process_full_document=True,
        source_chunks=[
            {"id": 11, "content": "Premier chunk", "content_hash": "hash-1"},
            {"id": 12, "content": "Deuxième chunk", "content_hash": "hash-2"},
            {"id": 13, "content": "Troisième chunk", "content_hash": "hash-3"},
        ],
    )

    worker = BatchWorker(tasks=[task])

    def fake_orchestrator_run(self_orch: Any) -> None:
        source = self_orch.state.get_variable("source_chunk")
        seen_sources.append(source)
        self_orch.state.variables["generated_cards"] = [{"Front": source, "Back": f"Réponse à {source}"}]

    monkeypatch.setattr(PipelineOrchestrator, "run", fake_orchestrator_run)
    completed: list[list[dict[str, Any]]] = []
    worker.task_completed.connect(lambda _idx, notes, _count: completed.append(notes))

    with qtbot.waitSignal(worker.batch_finished, timeout=5000) as blocker:
        worker.start()

    assert tuple(blocker.args) == (1, 0, 3)
    assert seen_sources == ["Premier chunk", "Deuxième chunk", "Troisième chunk"]
    assert [note["_source_chunk_id"] for note in completed[0]] == [11, 12, 13]


def test_batch_view_compose_button_and_hidden_full_document_option(qtbot: Any) -> None:
    """Le bouton unique de composition est présent et cb_full_document est masqué de l'UI."""
    view = BatchTab(ai_manager=None)
    qtbot.addWidget(view)
    assert hasattr(view, "btn_compose_batch")
    assert "Composer le lot" in view.btn_compose_batch.text()
    assert view.cb_full_document.isHidden() is True


def test_batch_view_chunk_to_queue_task_yields_independent_task(qtbot: Any) -> None:
    """Chaque partie sélectionnée (mode Direct) devient une tâche autonome à partir de son chunk."""
    doc = DocumentModel.create(title="Document Sections.md", content="Source", file_type="md")
    DocumentChunkModel.create(document=doc, chunk_index=0, content="Section A content", content_hash="section-a", heading_path="Section A")
    DocumentChunkModel.create(document=doc, chunk_index=1, content="Section B content", content_hash="section-b", heading_path="Section B")

    view = BatchTab(ai_manager=None)
    qtbot.addWidget(view)

    chunks = view._resolve_batch_chunks(doc)
    task_b = view._chunk_to_queue_task(doc, chunks[1])

    assert task_b is not None
    assert task_b["chunk_label"] == "Section B"
    assert task_b["source_chunks"][0]["content_hash"] == "section-b"
    assert task_b["doc_content"] == "Section B content"


def test_batch_worker_cancellation(qtbot: Any) -> None:
    """Vérifie que l'annulation interrompt le worker proprement."""
    task = BatchTaskPayload(
        task_index=0,
        doc_id=1,
        doc_title="Doc Cancel",
        doc_content="Cancel content",
        deck_id=1,
        deck_name="Deck",
        model_id=1,
        model_name="Model",
        note_type_fields=["Front", "Back"],
        note_type_templates=[],
        pipeline_id=1,
        pipeline_name="Standard",
        llm_id=1,
        llm_config={"provider": "mock", "model_id": "mock-model", "api_key": ""},
    )
    worker = BatchWorker(tasks=[task])
    worker.cancel()
    assert worker._is_cancelled is True


def test_batch_view_start_and_stop_button(qtbot: Any, monkeypatch: Any) -> None:
    """Vérifie le basculement dynamique du bouton Démarrer / Arrêter."""
    doc = DocumentModel.create(title="Doc Test Toggle.pdf", content_markdown="Data", file_type="pdf")
    view = BatchTab(ai_manager=None)
    qtbot.addWidget(view)

    # Composer et ajouter à la queue
    task = view._chunk_to_queue_task(doc, {"content": "Data", "title": "Section 1", "index": 0})
    assert task is not None
    view._append_queue_tasks([task])
    assert len(view.queue_tasks_data) >= 1

    # Simuler le passage à l'état en cours
    view._set_running_ui_state(True)
    assert "Arrêter" in view.btn_start_pipeline.text()

    # Simuler la fin du batch
    view._on_batch_finished(1, 0, 5)
    assert "Démarrer" in view.btn_start_pipeline.text()


def test_batch_view_full_execution_persists_notes_in_db(qtbot: Any, monkeypatch: Any) -> None:
    """Vérifie l'exécution complète depuis BatchView avec persistance effective en base de données."""
    deck = DeckModel.create(name="Deck Persist Batch")
    nt = NoteTypeModel.create(
        name="Model Persist Batch",
        fields_schema='["Front", "Back"]',
        templates=json.dumps([{"name": "Card 1", "qfmt": "{{Front}}", "afmt": "{{Back}}"}]),
        css_style="",
    )
    doc = DocumentModel.create(title="Doc Big.md", content="Contenu global", file_type="md")
    c1 = DocumentChunkModel.create(document=doc, chunk_index=0, content="Section 1 texte", heading_path="Section 1", content_hash="hash-sec-1")
    c2 = DocumentChunkModel.create(document=doc, chunk_index=1, content="Section 2 texte", heading_path="Section 2", content_hash="hash-sec-2")

    pipe = PipelineModel.create(name="Pipeline Persist")
    PipelineStepModel.create(pipeline=pipe, step_type="LLM_PROMPT", step_order=1, config_data=json.dumps({"prompt_template": "Test"}))
    LLMConfigModel.create(display_name="LLM Persist", provider="openai", model_id="gpt-4o", api_key="sk-test")

    view = BatchTab(ai_manager=None)
    qtbot.addWidget(view)
    view.refresh_data()

    view.current_deck = deck
    view.current_model = nt

    # Composition directe : 1 tâche par partie persistée du document
    chunk_tasks = [t for c in view._resolve_batch_chunks(doc) if (t := view._chunk_to_queue_task(doc, c)) is not None]
    view._append_queue_tasks(chunk_tasks)
    assert len(view.queue_tasks_data) == 2
    assert view.queue_tasks_data[0]["chunk_label"] == "Section 1"
    assert view.queue_tasks_data[1]["chunk_label"] == "Section 2"

    # Mock de l'exécution du DAG
    def fake_orchestrator_run(self_orch: Any) -> None:
        source = self_orch.state.get_variable("source_chunk") or self_orch.state.get_variable("text_source")
        self_orch.state.variables["generated_cards"] = [{"Front": f"Q pour {source}", "Back": f"A pour {source}"}]

    monkeypatch.setattr(PipelineOrchestrator, "run", fake_orchestrator_run)

    # Démarrer le batch (auto_validation par défaut désactivé → revue staging)
    view._on_start_batch()
    assert view.worker is not None

    with qtbot.waitSignal(view.worker.batch_finished, timeout=5000):
        pass

    # Par défaut, les cartes passent par la revue staging plutôt que d'être sauvegardées
    assert view.queue_tasks_data[0]["status"] == "À réviser"
    assert view.queue_tasks_data[1]["status"] == "À réviser"
    assert view.queue_tasks_data[0]["cards_count"] == 1
    assert view.queue_tasks_data[1]["cards_count"] == 1

    # Validation par le panneau de staging (équivalent clic 'Tout valider & Enregistrer')
    for idx in (0, 1):
        view._on_open_staging_for_task(idx)
        assert view.staging_panel._prepared_notes, f"Staging vide pour la tâche #{idx + 1}"
        view.staging_panel._on_accept_all()

    # Les liens notes→chunks sont créés par la sauvegarde batch (traçabilité documentaire)
    links = list(NoteChunkLinkModel.select().where(NoteChunkLinkModel.chunk.in_([c1, c2])))
    assert len(links) == 2
    linked_chunks = sorted([link.chunk_id for link in links])
    assert linked_chunks == sorted([c1.id, c2.id])
    cards = list(CardModel.select().where(CardModel.deck == deck))
    assert len(cards) == 2


def test_batch_view_sections_scope_restoration_and_queue(qtbot: Any, mock_db: Any) -> None:
    """Vérifie que BatchView mémorise la portée par section par document et l'injecte dans la queue."""
    from ankiforge.ui.dialogs.document_scope_dialog import DocumentScopeDialog

    deck = DeckModel.create(name="Deck Batch Sections")
    nt = NoteTypeModel.create(name="Model Batch Sections", fields_schema='["Front", "Back"]', templates="[]", css_style="")
    doc = DocumentModel.create(title="Manuel.pdf", file_type="pdf", total_pages=5)
    DocumentChunkModel.create(document=doc, chunk_index=0, page_number=1, heading_path="Intro", content="Contenu intro")
    DocumentChunkModel.create(document=doc, chunk_index=1, page_number=2, heading_path="Exercices", content="Contenu exercices")

    view = BatchTab(ai_manager=None)
    qtbot.addWidget(view)
    view.refresh_data()

    view.current_deck = deck
    view.current_model = nt

    # Enregistrer un scope_result ciblant uniquement la section 'Intro' pour ce document
    scope_res = {
        "chunks": [{"index": 0, "title": "Intro", "heading_path": "Intro", "page_number": 1, "content": "Contenu intro", "tokens": 12}],
        "scope_title": "Portée : 1 section(s) utile(s)",
        "scope_stats": "2 mots",
        "range_str": "",
        "start_page": 1,
        "end_page": 5,
        "selection_mode": "sections",
        "selected_headings": ["Intro"],
        "selected_chunk_indices": [0],
    }
    view._batch_scope_results[int(doc.id)] = scope_res

    # La mémoire de portée est bien restituée au composeur pour préremplir l'étape 1
    assert view._scope_memory_for(doc) == scope_res

    # Le mode Direct construit une tâche pour chaque partie retenue par la portée
    tasks = [t for c in scope_res["chunks"] if (t := view._chunk_to_queue_task(doc, c)) is not None]
    assert len(tasks) == 1
    assert tasks[0]["chunk_label"] == "Intro"
    assert tasks[0]["doc_content"] == "Contenu intro"

    # Vérification de la réouverture de la boîte de dialogue avec ce résultat mémorisé
    dlg = DocumentScopeDialog(doc, initial_scope_str="", initial_scope_result=view._batch_scope_results[int(doc.id)])
    qtbot.addWidget(dlg)
    assert dlg.selection_mode == "sections"
    assert dlg.btn_mode_sections.isChecked()
    chunks = dlg._selected_chunks_for_mode()
    assert len(chunks) == 1
    assert chunks[0]["heading_path"] == "Intro"


def test_batch_worker_resume_incomplete(qtbot: Any, monkeypatch: Any) -> None:
    """Vérifie que BatchWorker et BatchView ignorent les tâches réussies lors d'une reprise."""
    deck = DeckModel.create(name="Deck Worker Resume Test")
    nt = NoteTypeModel.create(
        name="Basic Worker Resume Test",
        fields_schema='["Front", "Back"]',
        templates=json.dumps([{"name": "Card 1", "qfmt": "{{Front}}", "afmt": "{{Back}}"}]),
        css_style="",
    )
    doc = DocumentModel.create(title="Doc Worker Resume.md", content_markdown="Source data", file_type="md")

    executed_tasks: list[int] = []

    def fake_orchestrator_run(self_orch: Any) -> None:
        idx = self_orch.state.get_variable("source_chunk_id") or 0
        executed_tasks.append(idx)
        self_orch.state.variables["generated_cards"] = [{"Front": f"Q {idx}", "Back": f"A {idx}"}]

    monkeypatch.setattr(PipelineOrchestrator, "run", fake_orchestrator_run)

    view = BatchTab(ai_manager=None)
    qtbot.addWidget(view)

    # Simuler 2 tâches dans la queue : tâche 0 déjà terminée, tâche 1 échouée
    t0 = {
        "doc": doc,
        "doc_id": doc.id,
        "doc_title": doc.title,
        "doc_content": "Chunk 0",
        "chunk_id": 101,
        "chunk_label": "Section 1",
        "heading_path": "S1",
        "page_number": 1,
        "deck": deck,
        "deck_id": deck.id,
        "deck_name": deck.name,
        "note_type": nt,
        "model_id": nt.id,
        "model_name": nt.name,
        "note_type_fields": ["Front", "Back"],
        "note_type_templates": [],
        "pipeline_id": 1,
        "pipeline_name": "Standard",
        "llm_id": 1,
        "llm_config": {"provider": "mock", "model_id": "mock-model", "api_key": ""},
        "status": "Succès",
        "cards_count": 2,
    }
    t1 = {
        "doc": doc,
        "doc_id": doc.id,
        "doc_title": doc.title,
        "doc_content": "Chunk 1",
        "chunk_id": 102,
        "chunk_label": "Section 2",
        "heading_path": "S2",
        "page_number": 2,
        "deck": deck,
        "deck_id": deck.id,
        "deck_name": deck.name,
        "note_type": nt,
        "model_id": nt.id,
        "model_name": nt.name,
        "note_type_fields": ["Front", "Back"],
        "note_type_templates": [],
        "pipeline_id": 1,
        "pipeline_name": "Standard",
        "llm_id": 1,
        "llm_config": {"provider": "mock", "model_id": "mock-model", "api_key": ""},
        "status": "Erreur",
        "cards_count": 0,
    }
    view.queue_tasks_data = [t0, t1]
    view._update_queue_table()
    view._update_resume_button_visibility()

    assert not view.btn_resume_batch.isHidden()

    # Déclencher la reprise
    view._on_resume_batch()
    assert view.worker is not None
    assert view.worker.resume_incomplete is True

    qtbot.waitUntil(
        lambda: view.queue_tasks_data[1]["status"] == "Succès" and view.btn_resume_batch.isHidden(),
        timeout=15000,
    )

    # Seule la tâche 1 a été exécutée par l'orchestrateur
    assert len(executed_tasks) == 1
    assert view.queue_tasks_data[0]["status"] == "Succès"
    assert view.queue_tasks_data[1]["status"] == "Succès"
    assert view.btn_resume_batch.isHidden()


# ── Atelier de production : 3 modes de composition ───────────────────────────


def test_batch_view_slice_to_queue_manual_task(qtbot: Any) -> None:
    """Le mode auto/wizard construit une tâche de file à partir d'un SliceUnit."""
    from ankiforge.services.batch.slicing_service import SlicingService

    doc = DocumentModel.create(
        title="Doc Slice.pdf",
        content="# Intro\n\nTexte introductif suffisamment long pour constituer une tranche d'étude.\n\n# Technique\n\nSecond paragraphe descriptif des méthodes utilisées.",
        file_type="pdf",
    )
    view = BatchTab(ai_manager=None)
    qtbot.addWidget(view)
    view.current_deck = None
    view.current_model = None

    slice_unit = SlicingService.slice_by_headings(doc.content, min_words=5)[0]
    task = view._slice_to_queue_task(doc, slice_unit)
    assert task is not None
    assert task["chunk_label"] == slice_unit.title
    assert task["doc_content"] == slice_unit.content
    assert task["source_chunks"][0]["content"] == slice_unit.content
    assert task["auto_val"] in (True, False)
    assert task["status"] == "En attente"


def test_batch_view_append_queue_tasks(qtbot: Any) -> None:
    """La file accepte des tâches composées via _append_queue_tasks."""
    doc = DocumentModel.create(title="Doc Compose.md", content="Contenu de la tranche", file_type="md")
    view = BatchTab(ai_manager=None)
    qtbot.addWidget(view)

    payload = {
        "doc": doc,
        "doc_title": "Doc Compose.md — Tranche 1",
        "doc_content": "Contenu de la tranche",
        "source_chunks": [{"content": "Contenu de la tranche"}],
        "chunk_label": "Tranche 1",
        "deck_name": "Général",
        "model_name": "Basique",
        "pipeline_name": "Standard",
    }
    view._append_queue_tasks([payload])
    assert len(view.queue_tasks_data) == 1
    assert view.queue_tasks_data[0]["status"] == "En attente"
    assert view.queue_tasks_data[0]["chunk_label"] == "Tranche 1"

    # Les entrées vides sont rejetées
    before = len(view.queue_tasks_data)
    view._append_queue_tasks([{"doc": doc, "doc_title": "Vide", "doc_content": "   "}])
    assert len(view.queue_tasks_data) == before


def test_batch_view_retry_failed_task(qtbot: Any) -> None:
    """Le bouton de relance remet une tâche en échec en attente."""
    doc = DocumentModel.create(title="Doc Retry.pdf", content="Contenu", file_type="pdf")
    view = BatchTab(ai_manager=None)
    qtbot.addWidget(view)
    view.queue_tasks_data = [
        {
            "doc": doc,
            "doc_title": "Doc Retry.pdf — Section 1",
            "doc_content": "Contenu",
            "chunk_label": "Section 1",
            "status": "Erreur",
            "progress_pct": 100,
            "cards_count": 0,
            "error_message": "boom",
            "deck_name": "Général",
            "model_name": "Basique",
            "pipeline_name": "Standard",
        }
    ]
    view._update_queue_table()
    view._on_retry_task(0)
    assert view.queue_tasks_data[0]["status"] == "En attente"


# ── Protocole scopes : BatchTaskSnapshot (BatchFactory) ─────────────────────


def _make_snapshot_task(
    deck: Any,
    nt: Any,
    doc: Any,
    pipe: Any,
    auto_validation: bool = True,
    temperature: float = 0.7,
    provider: str = "mock",
    max_tokens: int = 2048,
) -> Any:
    from ankiforge.services.batch.models import (
        BatchGenerationConfig,
        BatchScopeSnapshot,
        BatchSourceBlock,
        BatchTaskSnapshot,
    )

    block = BatchSourceBlock(
        kind="section",
        label="Intro",
        content="Source intro",
        ordinal=0,
        page_number=1,
        heading_path="Intro",
        source_id=doc.id,
    )
    scope = BatchScopeSnapshot(document_id=doc.id, document_title=doc.title, selection_mode="sections", blocks=(block,), scope_title="Intro")
    config = BatchGenerationConfig(
        pipeline_id=pipe.id,
        pipeline_name=pipe.name,
        llm_id=1,
        llm_config={"provider": provider, "model_id": "mock-model" if provider == "mock" else "default", "api_key": ""},
        deck_id=deck.id,
        deck_name=deck.name,
        model_id=nt.id,
        model_name=nt.name,
        note_type_fields=("Front", "Back"),
        note_type_templates=({"name": "Card 1", "qfmt": "{{Front}}", "afmt": "{{Back}}"},),
        auto_validation=auto_validation,
        use_vision=False,
        temperature=temperature,
        max_tokens=max_tokens,
        strict_source_grounding=True,
    )
    return BatchTaskSnapshot.create(scope=scope, config=config)


def test_batch_worker_scope_propagates_generation_vars_into_state(qtbot: Any, monkeypatch: Any) -> None:
    """Le chemin par portées injecte température/max_tokens/use_vision dans l'état du DAG."""
    from ankiforge.services.ai.base import MockProvider
    from ankiforge.services.batch.models import BatchTaskStatus

    deck = DeckModel.create(name="Deck Snapshot")
    nt = NoteTypeModel.create(
        name="NT Snapshot",
        fields_schema='["Front", "Back"]',
        templates=json.dumps([{"name": "Card 1", "qfmt": "{{Front}}", "afmt": "{{Back}}"}]),
    )
    doc = DocumentModel.create(title="Doc Snapshot.md", content_markdown="x", file_type="md")
    pipe = PipelineModel.create(name="Pipeline Snapshot")
    PipelineStepModel.create(pipeline=pipe, step_type="LLM_PROMPT", step_order=1, config_data='{"prompt_template": "Prompt"}')

    task = _make_snapshot_task(deck, nt, doc, pipe, auto_validation=False, temperature=0.42, max_tokens=2048)
    captured: dict[str, Any] = {}

    def fake_run(self_orch: Any) -> None:
        captured["temperature"] = self_orch.state.get_variable("temperature")
        captured["max_tokens"] = self_orch.state.get_variable("max_tokens")
        captured["use_vision"] = self_orch.state.get_variable("use_vision")
        captured["blocks"] = len(self_orch.state.get_variable("source_blocks") or [])
        self_orch.state.variables["generated_cards"] = [{"Front": "Q", "Back": "A"}]

    monkeypatch.setattr(PipelineOrchestrator, "run", fake_run)

    worker = BatchWorker(tasks=[task])
    worker.ai_provider = MockProvider()
    states: list[tuple[int, str]] = []
    reviews: list[tuple[int, list[Any]]] = []
    worker.task_state_changed.connect(lambda idx, st: states.append((idx, st)))
    worker.task_review_ready.connect(lambda idx, cards: reviews.append((idx, cards)))

    with qtbot.waitSignal(worker.batch_finished, timeout=5000) as blocker:
        worker.start()

    success_count, fail_count, total_cards = blocker.args
    assert (success_count, fail_count, total_cards) == (1, 0, 1)
    assert captured["temperature"] == 0.42
    assert captured["max_tokens"] == 2048
    assert captured["use_vision"] is False
    assert captured["blocks"] == 1
    assert task.status == BatchTaskStatus.REVIEW
    assert states[-1] == (0, "review")
    assert reviews and reviews[0][0] == 0 and len(reviews[0][1]) == 1


def test_batch_worker_scope_auto_validation_routes_accepted(qtbot: Any, monkeypatch: Any) -> None:
    """Auto-validation : une tâche de portée passe en ACCEPTED (persistance côté vue)."""
    from ankiforge.services.ai.base import MockProvider
    from ankiforge.services.batch.models import BatchTaskStatus

    deck = DeckModel.create(name="Deck Snapshot Auto")
    nt = NoteTypeModel.create(name="NT Snapshot Auto", fields_schema='["Front", "Back"]', templates="[]", css_style="")
    doc = DocumentModel.create(title="Doc Snapshot Auto.md", content_markdown="x", file_type="md")
    pipe = PipelineModel.create(name="Pipeline Snapshot Auto")
    PipelineStepModel.create(pipeline=pipe, step_type="LLM_PROMPT", step_order=1, config_data='{"prompt_template": "Prompt"}')

    task = _make_snapshot_task(deck, nt, doc, pipe, auto_validation=True)

    def fake_run(self_orch: Any) -> None:
        self_orch.state.variables["generated_cards"] = [{"Front": "Q", "Back": "A"}]

    monkeypatch.setattr(PipelineOrchestrator, "run", fake_run)

    worker = BatchWorker(tasks=[task])
    worker.ai_provider = MockProvider()
    states: list[tuple[int, str]] = []
    accepted: list[tuple[int, int]] = []
    worker.task_state_changed.connect(lambda idx, st: states.append((idx, st)))
    worker.task_accepted.connect(lambda idx, count: accepted.append((idx, count)))

    with qtbot.waitSignal(worker.batch_finished, timeout=5000):
        worker.start()

    assert task.status == BatchTaskStatus.ACCEPTED
    assert states[-1] == (0, "accepted")
    assert accepted == [(0, 1)]


def test_batch_worker_scope_human_validation_forced_review(qtbot: Any, monkeypatch: Any) -> None:
    """Une étape HUMAN_VALIDATION contournée force le retour en revue, même en auto-validation."""
    from ankiforge.services.ai.base import MockProvider
    from ankiforge.services.batch.models import BatchTaskStatus

    deck = DeckModel.create(name="Deck Snapshot Human")
    nt = NoteTypeModel.create(name="NT Snapshot Human", fields_schema='["Front", "Back"]', templates="[]", css_style="")
    doc = DocumentModel.create(title="Doc Snapshot Human.md", content_markdown="x", file_type="md")
    pipe = PipelineModel.create(name="Pipeline Snapshot Human")
    PipelineStepModel.create(pipeline=pipe, step_type="LLM_PROMPT", step_order=1, config_data='{"prompt_template": "Prompt"}')

    # auto_validation=True mais l'étape exige une validation humaine → revue systématique.
    task = _make_snapshot_task(deck, nt, doc, pipe, auto_validation=True)

    def fake_run(self_orch: Any) -> None:
        self_orch.signals.human_validation_required.emit(self_orch.state)
        self_orch.state.variables["generated_cards"] = [{"Front": "Q", "Back": "A"}]

    monkeypatch.setattr(PipelineOrchestrator, "run", fake_run)

    worker = BatchWorker(tasks=[task])
    worker.ai_provider = MockProvider()
    states: list[tuple[int, str]] = []
    worker.task_state_changed.connect(lambda idx, st: states.append((idx, st)))

    with qtbot.waitSignal(worker.batch_finished, timeout=5000) as blocker:
        worker.start()

    success_count, fail_count, _ = blocker.args
    assert (success_count, fail_count) == (1, 0)
    assert task.status == BatchTaskStatus.REVIEW
    assert states[-1] == (0, "review")


def test_batch_worker_blocks_mockprovider_fallback_for_real_provider(qtbot: Any, monkeypatch: Any) -> None:
    """Le repli silencieux sur MockProvider est bloqué pour un provider réel sans clé."""
    from ankiforge.services.batch.models import BatchTaskStatus

    deck = DeckModel.create(name="Deck Snapshot Guard")
    nt = NoteTypeModel.create(name="NT Snapshot Guard", fields_schema='["Front", "Back"]', templates="[]", css_style="")
    doc = DocumentModel.create(title="Doc Snapshot Guard.md", content_markdown="x", file_type="md")
    pipe = PipelineModel.create(name="Pipeline Snapshot Guard")
    PipelineStepModel.create(pipeline=pipe, step_type="LLM_PROMPT", step_order=1, config_data='{"prompt_template": "Prompt"}')

    task = _make_snapshot_task(deck, nt, doc, pipe, provider="openai", auto_validation=True)

    def fake_run(self_orch: Any) -> None:
        self_orch.state.variables["generated_cards"] = [{"Front": "Q", "Back": "A"}]

    monkeypatch.setattr(PipelineOrchestrator, "run", fake_run)

    worker = BatchWorker(tasks=[task])
    states: list[tuple[int, str]] = []
    worker.task_state_changed.connect(lambda idx, st: states.append((idx, st)))

    with qtbot.waitSignal(worker.batch_finished, timeout=5000) as blocker:
        worker.start()

    success_count, fail_count, total_cards = blocker.args
    assert (success_count, fail_count, total_cards) == (0, 1, 0)
    assert task.status == BatchTaskStatus.FAILED
    assert "MockProvider" in (task.error or "")
    assert states[-1] == (0, "failed")


def test_batch_worker_mixed_snapshot_and_legacy_dispatch(qtbot: Any, monkeypatch: Any) -> None:
    """Une file mixte (portées + legacy) est traitée séquentiellement avec les bons index de file."""
    from ankiforge.services.ai.base import MockProvider

    deck = DeckModel.create(name="Deck Snapshot Mix")
    nt = NoteTypeModel.create(name="NT Snapshot Mix", fields_schema='["Front", "Back"]', templates="[]", css_style="")
    doc = DocumentModel.create(title="Doc Snapshot Mix.md", content_markdown="x", file_type="md")
    pipe = PipelineModel.create(name="Pipeline Snapshot Mix")
    PipelineStepModel.create(pipeline=pipe, step_type="LLM_PROMPT", step_order=1, config_data='{"prompt_template": "Prompt"}')

    legacy = BatchTaskPayload(
        task_index=0,
        doc_id=doc.id,
        doc_title=doc.title,
        doc_content="Legacy content",
        deck_id=deck.id,
        deck_name=deck.name,
        model_id=nt.id,
        model_name=nt.name,
        note_type_fields=["Front", "Back"],
        note_type_templates=[],
        pipeline_id=pipe.id,
        pipeline_name=pipe.name,
        llm_id=1,
        llm_config={"provider": "mock", "model_id": "mock-model", "api_key": ""},
        auto_validation=False,
    )
    snapshot = _make_snapshot_task(deck, nt, doc, pipe, auto_validation=False)

    worker = BatchWorker(tasks=[legacy, snapshot])
    worker.ai_provider = MockProvider()

    def fake_run(self_orch: Any) -> None:
        self_orch.state.variables["generated_cards"] = [{"Front": "Q", "Back": "A"}]

    monkeypatch.setattr(PipelineOrchestrator, "run", fake_run)

    completed: list[tuple[int, int]] = []
    states: list[tuple[int, str]] = []
    worker.task_completed.connect(lambda idx, notes, count: completed.append((idx, count)))
    worker.task_state_changed.connect(lambda idx, st: states.append((idx, st)))

    with qtbot.waitSignal(worker.batch_finished, timeout=5000) as blocker:
        worker.start()

    success_count, fail_count, total_cards = blocker.args
    assert (success_count, fail_count, total_cards) == (2, 0, 2)
    # Index absolus de la file d'attente (portée = position 1), pas des sous-listes.
    assert sorted(idx for idx, _ in completed) == [0, 1]
    # La portée (exécutée en premier) rapporte bien son index absolu de file : 1.
    assert completed[0][0] == 1
    assert states[-1] == (1, "review")


def test_batch_view_starts_snapshot_worker_from_scope_memory(qtbot: Any, monkeypatch: Any, mock_db: Any) -> None:
    """BatchView construit un BatchTaskSnapshot depuis la mémoire de portée du composer Direct."""
    deck = DeckModel.create(name="Deck View Snapshot")
    nt = NoteTypeModel.create(
        name="NT View Snapshot",
        fields_schema='["Front", "Back"]',
        templates=json.dumps([{"name": "Card 1", "qfmt": "{{Front}}", "afmt": "{{Back}}"}]),
    )
    doc = DocumentModel.create(title="Doc View Snapshot.md", content_markdown="s", file_type="md")
    pipe = PipelineModel.create(name="Pipeline View Snapshot")
    PipelineStepModel.create(pipeline=pipe, step_type="LLM_PROMPT", step_order=1, config_data='{"prompt_template": "Prompt"}')

    view = BatchTab(ai_manager=None)
    qtbot.addWidget(view)
    view.queue_tasks_data = []
    view.current_deck = deck
    view.current_model = nt

    scope_res = {
        "parts": [{"index": 0, "title": "Intro", "heading_path": "Intro", "page_number": 1, "content": "Source intro", "tokens": 8}],
        "selection_mode": "sections",
    }
    view._batch_scope_results[int(doc.id)] = scope_res
    part = scope_res["parts"][0]
    row = {
        "doc": doc,
        "doc_title": f"{doc.title} — Intro",
        "doc_content": part["content"],
        "source_chunks": [part],
        "chunk_label": "Intro",
        "chunk_index": 0,
        "deck": deck,
        "note_type": nt,
        "pipeline": pipe,
        "llm_config": {"provider": "mock", "model_id": "mock-model", "api_key": ""},
        "auto_val": True,
        "use_vision": False,
        "temperature": 0.7,
        "max_tokens": 16384,
        "status": "En attente",
        "progress_pct": 0,
        "cards_count": 0,
        "pending_cards": [],
    }
    view._append_queue_tasks([row])

    def fake_run(self_orch: Any) -> None:
        self_orch.state.variables["generated_cards"] = [{"Front": "Q ?", "Back": "A ."}]

    monkeypatch.setattr(PipelineOrchestrator, "run", fake_run)

    assert view._snapshot_scope_for_task(row) is not None
    view._on_start_batch()
    assert isinstance(view.worker.tasks[0], BatchTaskSnapshot)

    qtbot.waitUntil(lambda: view.queue_tasks_data[0]["status"] == "Succès", timeout=15000)
    assert len(list(NoteModel.select())) == 1


def test_batch_view_retry_cap_blocks_snapshot_task_after_three_attempts(qtbot: Any) -> None:
    """La relance d'une tâche de portée en échec est bloquée au bout de 3 tentatives."""
    doc = DocumentModel.create(title="Doc Retry Cap.pdf", content="Contenu", file_type="pdf")
    view = BatchTab(ai_manager=None)
    qtbot.addWidget(view)
    view.queue_tasks_data = [
        {
            "doc": doc,
            "doc_title": "Doc Retry Cap.pdf — Section 1",
            "doc_content": "Contenu",
            "chunk_label": "Section 1",
            "_is_snapshot_task": True,
            "_attempt_count": 3,
            "status": "Erreur",
            "progress_pct": 100,
            "cards_count": 0,
            "error_message": "boom",
        }
    ]
    view._update_queue_table()
    view._on_retry_task(0)
    # Plafond atteint : la tâche reste en erreur, aucune relance n'est déclenchée.
    assert view.queue_tasks_data[0]["status"] == "Erreur"
    assert view.worker is None
    assert view.queue_tasks_data[0].get("error_message") == "boom"


def test_batch_view_autoval_default_is_staging_review(qtbot: Any) -> None:
    """La validation automatique est désactivée par défaut : les cartes passent par la revue staging."""
    view = BatchTab(ai_manager=None)
    qtbot.addWidget(view)
    assert view.cb_autoval.isChecked() is False
    assert view._default_queue_targets()["auto_val"] is False
    assert view.metrics_bar.card_cards.cursor().shape() == Qt.CursorShape.PointingHandCursor


def test_batch_staging_panel_navigation_and_no_clobber(qtbot: Any) -> None:
    """La revue agrégée navigue entre tranches et n'écrase pas une revue en cours sur < >."""

    doc = DocumentModel.create(title="Doc Revue Agregée.md", content="Contenu", file_type="md")
    view = BatchTab(ai_manager=None)
    qtbot.addWidget(view)

    tasks = [
        {"doc": doc, "doc_title": "Doc — Section 1", "status": "À réviser", "_staging_notes": [{"Front": "Q1", "Back": "A1"}]},
        {"doc": doc, "doc_title": "Doc — Section 2", "status": "À réviser", "_staging_notes": [{"Front": "Q2", "Back": "A2"}]},
        {"doc": doc, "doc_title": "Doc — Section 3", "status": "Erreur", "_staging_notes": [{"Front": "Q3", "Back": "A3"}]},
    ]
    view.queue_tasks_data = tasks
    panel = view.staging_panel
    panel.set_review_tasks_provider(view._staging_task_list)

    # Panel rendu visible pour réellement simuler une revue 'en cours'
    view.show()
    qtbot.wait(20)

    # Charge une revue puis navigue : la revue en cours N'EST PAS écrasée par un chargement automatique
    panel.load_task(0, tasks[0], tasks[0]["_staging_notes"], force=True)
    view.main_splitter.sizes()
    assert len(view.main_splitter.sizes()) == 3 and view.main_splitter.sizes()[2] > 0, "Le panneau de revue doit recevoir une vraie hauteur dans le splitter (régression taille 0)."
    panel.load_task(1, tasks[1], tasks[1]["_staging_notes"], force=False)
    assert panel._current_task_idx == 0, "Un chargement auto ne doit pas écraser la revue en cours"
    panel.load_task(2, tasks[2], tasks[2]["_staging_notes"], force=True)
    assert panel._current_task_idx == 2, "Un clic 'Examiner' force la revue demandée"

    # Navigation '< >' : ne visite que les tâches 'À réviser' (3 exclue → boucle sur [0, 1])
    panel._nav_to_task(1)
    assert panel._current_task_idx == 0
    panel._nav_to_task(1)
    assert panel._current_task_idx == 1
    assert panel._prepared_notes[0]["Front"] == "Q2"

    # Bascule de statut par carte (clic droit) sans sauvegarde
    panel._nav_to_task(-1)
    panel._toggle_card_status(0, "rejected")
    assert panel._prepared_notes[0]["_staging_status"] == "rejected"
    panel._toggle_card_status(0, "rejected")
    assert panel._prepared_notes[0]["_staging_status"] == "pending"


def test_batch_staging_accept_all_skips_rejected_cards(qtbot: Any) -> None:
    """Valider tout respecte les rejets individuels et conserve la provenance _source_*."""
    doc = DocumentModel.create(title="Doc Rejets.md", content="Contenu", file_type="md")
    deck = DeckModel.create(name="Deck Rejets")
    nt = NoteTypeModel.create(name="Model Rejets", fields_schema='["Front", "Back"]', templates="[]", css_style="")
    view = BatchTab(ai_manager=None)
    qtbot.addWidget(view)

    task = {"doc": doc, "deck": deck, "note_type": nt, "doc_title": "Doc — Section 1", "status": "À réviser"}
    panel = view.staging_panel
    saved: list[tuple[list[dict[str, Any]], int, int, int]] = []
    panel.set_save_callback(lambda notes, deck_id, model_id, doc_id: saved.append((notes, deck_id, model_id, doc_id)))

    panel.load_task(
        0,
        task,
        [
            {"Front": "Gardée", "_source_chunk_id": 3},
            {"Front": "Rejetée", "_source_chunk_id": 4},
        ],
        force=True,
    )
    panel._toggle_card_status(1, "rejected")
    panel._on_accept_all()

    assert len(saved) == 1
    notes, deck_id, model_id, doc_id = saved[0]
    assert deck_id == deck.id and model_id == nt.id and doc_id == doc.id
    assert len(notes) == 1, "La carte rejetée ne doit pas être sauvegardée"
    assert notes[0]["Front"] == "Gardée"
    assert notes[0]["_source_chunk_id"] == 3, "La provenance _source_* doit être conservée par le staging"
    assert "_staging_status" not in notes[0]


def test_batch_staging_fine_grained_card_validation_and_navigation(qtbot: Any) -> None:
    """Vérifie la navigation unitaire (<, >), la validation/rejet au fil de l'eau et le décompte."""
    doc = DocumentModel.create(title="Doc Granulaire.md", content="Contenu", file_type="md")
    deck = DeckModel.create(name="Deck Granulaire")
    nt = NoteTypeModel.create(name="Model Granulaire", fields_schema='["Front", "Back"]', templates="[]", css_style="")
    view = BatchTab(ai_manager=None)
    qtbot.addWidget(view)

    task = {"doc": doc, "deck": deck, "note_type": nt, "doc_title": "Doc — Section 1", "status": "À réviser"}
    panel = view.staging_panel
    panel.load_task(
        0,
        task,
        [
            {"Front": "Carte 1", "Back": "R1"},
            {"Front": "Carte 2", "Back": "R2"},
            {"Front": "Carte 3", "Back": "R3"},
        ],
        force=True,
    )

    # État initial
    assert panel.lbl_card_counter.text() == "1 / 3"
    assert "En attente" in panel.status_badge.text()
    assert panel.btn_save_anki.text() == "Enregistrer dans la Forge (0/3)"

    # Navigation vers l'avant puis l'arrière
    panel._on_next_card()
    assert panel.lbl_card_counter.text() == "2 / 3"
    panel._on_prev_card()
    assert panel.lbl_card_counter.text() == "1 / 3"

    # Validation de la 1ère carte -> avance automatique à la 2ème
    panel._on_validate_card()
    assert panel._prepared_notes[0]["_staging_status"] == "accepted"
    assert panel._current_card_idx == 1
    assert panel.lbl_card_counter.text() == "2 / 3"
    assert panel.btn_save_anki.text() == "Enregistrer dans la Forge (1/3)"

    # Rejet de la 2ème carte -> avance à la 3ème
    panel._on_reject_card()
    assert panel._prepared_notes[1]["_staging_status"] == "rejected"
    assert panel._current_card_idx == 2
    assert panel.lbl_card_counter.text() == "3 / 3"
    assert panel.btn_save_anki.text() == "Enregistrer dans la Forge (1/3)"

    # Revenir sur la 1ère carte et vérifier son badge
    panel._select_card(0)
    assert panel.lbl_card_counter.text() == "1 / 3"
    assert "Validée" in panel.status_badge.text()


def test_batch_staging_multi_selection_and_mark_all(qtbot: Any) -> None:
    """Vérifie le comportement avec multi-sélection et l'action 1-clic 'Tout valider'."""
    doc = DocumentModel.create(title="Doc Multi.md", content="Contenu", file_type="md")
    deck = DeckModel.create(name="Deck Multi")
    nt = NoteTypeModel.create(name="Model Multi", fields_schema='["Front", "Back"]', templates="[]", css_style="")
    view = BatchTab(ai_manager=None)
    qtbot.addWidget(view)

    task = {"doc": doc, "deck": deck, "note_type": nt, "doc_title": "Doc — Section Multi", "status": "À réviser"}
    panel = view.staging_panel
    panel.load_task(
        0,
        task,
        [
            {"Front": "C1", "Back": "R1"},
            {"Front": "C2", "Back": "R2"},
            {"Front": "C3", "Back": "R3"},
            {"Front": "C4", "Back": "R4"},
        ],
        force=True,
    )

    # Sélectionner les lignes 1 et 2
    from PySide6.QtCore import QItemSelection, QItemSelectionModel

    panel.cards_table.clearSelection()
    sel = QItemSelection(panel.cards_table.model().index(1, 0), panel.cards_table.model().index(2, 2))
    panel.cards_table.selectionModel().select(sel, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
    panel._on_table_selection_changed()

    assert "sélection (2)" in panel.btn_valider.text()
    assert "sélection (2)" in panel.btn_rejeter.text()

    # Valider la sélection de 2 cartes : elles passent en 'accepted' sans fermer le staging
    panel._on_validate_card()
    assert not panel.isHidden()
    assert panel._prepared_notes[1]["_staging_status"] == "accepted"
    assert panel._prepared_notes[2]["_staging_status"] == "accepted"
    assert panel.btn_save_anki.text() == "Enregistrer dans la Forge (2/4)"

    # Action 1-clic "Tout valider" : bascule toutes les cartes non-rejetées
    panel._on_mark_all_accepted()
    assert not panel.isHidden()
    assert all(c["_staging_status"] == "accepted" for c in panel._prepared_notes)
    assert panel.btn_save_anki.text() == "Enregistrer dans la Forge (4/4)"


def test_batch_staging_keyboard_shortcuts(qtbot: Any) -> None:
    """Vérifie que les raccourcis clavier V et R fonctionnent via l'eventFilter."""
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QKeyEvent

    doc = DocumentModel.create(title="Doc Shortcuts.md", content="Contenu", file_type="md")
    deck = DeckModel.create(name="Deck Shortcuts")
    nt = NoteTypeModel.create(name="Model Shortcuts", fields_schema='["Front", "Back"]', templates="[]", css_style="")
    view = BatchTab(ai_manager=None)
    qtbot.addWidget(view)

    task = {"doc": doc, "deck": deck, "note_type": nt, "doc_title": "Doc — Section Shortcuts", "status": "À réviser"}
    panel = view.staging_panel
    panel.load_task(
        0,
        task,
        [
            {"Front": "Key 1", "Back": "R1"},
            {"Front": "Key 2", "Back": "R2"},
        ],
        force=True,
    )

    # Simuler appui sur 'V' (Valider)
    event_v = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_V, Qt.KeyboardModifier.NoModifier, "v")
    consumed = panel.eventFilter(panel.cards_table, event_v)
    assert consumed is True
    assert panel._prepared_notes[0]["_staging_status"] == "accepted"
    assert panel._current_card_idx == 1

    # Simuler appui sur 'R' (Rejeter)
    event_r = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_R, Qt.KeyboardModifier.NoModifier, "r")
    consumed_r = panel.eventFilter(panel.cards_table, event_r)
    assert consumed_r is True
    assert panel._prepared_notes[1]["_staging_status"] == "rejected"


def test_batch_start_pipeline_skips_already_successful_tasks(qtbot: Any, monkeypatch: Any) -> None:
    """Cliquer sur 'Démarrer Pipeline' ignore les tâches déjà en Succès et ne traite que les nouvelles."""
    deck = DeckModel.create(name="Deck Start Skip Test")
    nt = NoteTypeModel.create(
        name="Basic Start Skip Test",
        fields_schema='["Front", "Back"]',
        templates=json.dumps([{"name": "Card 1", "qfmt": "{{Front}}", "afmt": "{{Back}}"}]),
        css_style="",
    )
    doc = DocumentModel.create(title="Doc Start Skip.md", content_markdown="Source data", file_type="md")

    executed_contents: list[str] = []

    def fake_orchestrator_run(self_orch: Any) -> None:
        content = str(self_orch.state.get_variable("text_source") or "")
        executed_contents.append(content)
        self_orch.state.variables["generated_cards"] = [{"Front": f"Q {content}", "Back": f"A {content}"}]

    monkeypatch.setattr(PipelineOrchestrator, "run", fake_orchestrator_run)

    view = BatchTab(ai_manager=None)
    qtbot.addWidget(view)

    # 1. Tâche 0 déjà terminée avec succès (3 cartes)
    t0 = {
        "doc": doc,
        "doc_id": doc.id,
        "doc_title": doc.title,
        "doc_content": "Chunk 0",
        "chunk_id": 201,
        "chunk_label": "Section 1",
        "heading_path": "S1",
        "page_number": 1,
        "deck": deck,
        "deck_id": deck.id,
        "deck_name": deck.name,
        "note_type": nt,
        "model_id": nt.id,
        "model_name": nt.name,
        "note_type_fields": ["Front", "Back"],
        "note_type_templates": [],
        "pipeline_id": 1,
        "pipeline_name": "Standard",
        "llm_id": 1,
        "llm_config": {"provider": "mock", "model_id": "mock-model", "api_key": ""},
        "status": "Succès",
        "cards_count": 3,
    }
    # 2. Nouvelle tâche 1 ajoutée par l'utilisateur ("En attente")
    t1 = {
        "doc": doc,
        "doc_id": doc.id,
        "doc_title": doc.title,
        "doc_content": "Chunk 1",
        "chunk_id": 202,
        "chunk_label": "Section 2",
        "heading_path": "S2",
        "page_number": 2,
        "deck": deck,
        "deck_id": deck.id,
        "deck_name": deck.name,
        "note_type": nt,
        "model_id": nt.id,
        "model_name": nt.name,
        "note_type_fields": ["Front", "Back"],
        "note_type_templates": [],
        "pipeline_id": 1,
        "pipeline_name": "Standard",
        "llm_id": 1,
        "llm_config": {"provider": "mock", "model_id": "mock-model", "api_key": ""},
        "status": "En attente",
        "cards_count": 0,
    }

    view.queue_tasks_data = [t0, t1]
    view._update_queue_table()

    # Démarrage normal (via clic sur btn_start_pipeline qui passe resume_incomplete=False)
    view._on_start_batch(resume_incomplete=False)
    assert view.worker is not None

    qtbot.waitUntil(
        lambda: view.queue_tasks_data[1]["status"] == "Succès" and view.worker is not None and not view.worker.isRunning(),
        timeout=15000,
    )

    # Tâche 0 est restée intouchée en Succès avec ses 3 cartes initiales
    assert view.queue_tasks_data[0]["status"] == "Succès"
    assert view.queue_tasks_data[0]["cards_count"] == 3

    # Seul le chunk 1 a été exécuté (tâche 0 sautée car déjà en Succès)
    assert executed_contents == ["Chunk 1"]

    # Total accumulé = 3 (t0) + 1 (t1 généré par mock)
    assert view._total_cards_accumulated == 4

    # Si on ré-exécute alors que tout est à Succès : aucun worker n'est relancé
    prev_worker = view.worker
    view._on_start_batch(resume_incomplete=False)
    assert view.worker is prev_worker

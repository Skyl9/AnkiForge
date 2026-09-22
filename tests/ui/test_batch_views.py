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

    # Vérification des listes et combos
    assert view.docs_list.count() >= 2

    # Vérification des sélecteurs de Deck et Modèle
    assert view.btn_select_deck.text() != ""
    assert view.btn_select_model.text() != ""

    # Vérification du sélecteur de Pipeline
    pipe_names = [view.pipeline_combo.itemText(i) for i in range(view.pipeline_combo.count())]
    assert any(pipe.name in name for name in pipe_names)

    # Vérification du sélecteur de Moteur IA
    engine_names = [view.engine_combo.itemText(i) for i in range(view.engine_combo.count())]
    assert any("gpt-4o-mini" in name or "LLM Test" in name for name in engine_names)


def test_batch_view_search_and_check_actions(qtbot: Any) -> None:
    """Vérifie le filtrage textuel et les boutons Tout cocher / Tout décocher."""
    DocumentModel.create(title="Physique Quantique.pdf", content_markdown="Quantum", file_type="pdf")
    DocumentModel.create(title="Biologie Cellulaire.pdf", content_markdown="Cells", file_type="pdf")

    view = BatchTab(ai_manager=None)
    qtbot.addWidget(view)

    # Filtrer avec recherche
    view.doc_search_input.setText("Physique")
    hidden_count = 0
    visible_count = 0
    for i in range(view.docs_list.count()):
        item = view.docs_list.item(i)
        if item.isHidden():
            hidden_count += 1
        else:
            visible_count += 1
    assert visible_count >= 1

    # Réinitialiser recherche
    view.doc_search_input.setText("")

    # Tout cocher
    view._set_all_docs_checked(True)
    for i in range(view.docs_list.count()):
        if not view.docs_list.item(i).isHidden():
            assert view.docs_list.item(i).checkState() == Qt.CheckState.Checked

    assert "sélectionné" in view.lbl_selected_docs_count.text()

    # Tout décocher
    view._set_all_docs_checked(False)
    for i in range(view.docs_list.count()):
        assert view.docs_list.item(i).checkState() == Qt.CheckState.Unchecked
    assert "0 sélectionné(s)" in view.lbl_selected_docs_count.text()


def test_batch_view_queue_management(qtbot: Any) -> None:
    """Vérifie l'ajout, la suppression unitaire et le vidage de la file d'attente."""
    doc = DocumentModel.create(title="Document File Test.pdf", content_markdown="File test", file_type="pdf")

    view = BatchTab(ai_manager=None)
    qtbot.addWidget(view)

    # Cocher un document
    for i in range(view.docs_list.count()):
        item = view.docs_list.item(i)
        target_doc = item.data(Qt.ItemDataRole.UserRole)
        if target_doc and getattr(target_doc, "id", None) == doc.id:
            item.setCheckState(Qt.CheckState.Checked)
            break

    # Ajouter à la file
    view._on_add_to_queue_clicked()
    assert len(view.queue_tasks_data) >= 1
    assert view.queue_table.rowCount() >= 1

    initial_count = len(view.queue_tasks_data)

    # Supprimer la première tâche
    view._remove_from_queue(0)
    assert len(view.queue_tasks_data) == initial_count - 1

    # Ajouter à nouveau puis vider toute la file
    for i in range(view.docs_list.count()):
        item = view.docs_list.item(i)
        if item.data(Qt.ItemDataRole.UserRole) and getattr(item.data(Qt.ItemDataRole.UserRole), "id", None) == doc.id:
            item.setCheckState(Qt.CheckState.Checked)
            break
    view._on_add_to_queue_clicked()
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


def test_batch_view_has_delimit_button_and_hidden_full_document_option(qtbot: Any) -> None:
    """Le bouton de délimitation est présent et cb_full_document est masqué de l'UI."""
    view = BatchTab(ai_manager=None)
    qtbot.addWidget(view)
    assert hasattr(view, "btn_delimit_doc")
    assert "Délimiter" in view.btn_delimit_doc.text() and "Découper" in view.btn_delimit_doc.text()
    assert view.cb_full_document.isHidden() is True


def test_batch_queue_expands_selected_chunks_into_independent_rows(qtbot: Any) -> None:
    """Chaque chunk sélectionné dans le modal/inspecteur devient une tâche autonome."""
    doc = DocumentModel.create(title="Document Sections.md", content="Source", file_type="md")
    DocumentChunkModel.create(document=doc, chunk_index=0, content="Section A content", content_hash="section-a", heading_path="Section A")
    DocumentChunkModel.create(document=doc, chunk_index=1, content="Section B content", content_hash="section-b", heading_path="Section B")

    view = BatchTab(ai_manager=None)
    qtbot.addWidget(view)
    view._segment_inspector_doc = doc
    view.segment_inspector.set_document(doc)
    view.segment_inspector._chunks = view._resolve_batch_chunks(doc)
    view.segment_inspector._refresh_list_ui()
    view.doc_picker_btn.set_document(doc, emit_signal=False)

    view.segment_inspector._set_all_checked(False)
    second_item = view.segment_inspector.segments_list.item(1)
    second_item.setCheckState(Qt.CheckState.Checked)
    second_widget = view.segment_inspector.segments_list.itemWidget(second_item)
    second_widget.set_checked(True)
    view._on_add_to_queue_clicked()

    assert len(view.queue_tasks_data) == 1
    assert view.queue_tasks_data[0]["chunk_label"] == "Section B"
    assert view.queue_tasks_data[0]["source_chunks"][0]["content_hash"] == "section-b"


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

    # Cocher et ajouter à la queue
    for i in range(view.docs_list.count()):
        item = view.docs_list.item(i)
        if item.data(Qt.ItemDataRole.UserRole) and getattr(item.data(Qt.ItemDataRole.UserRole), "id", None) == doc.id:
            item.setCheckState(Qt.CheckState.Checked)
            break
    view._on_add_to_queue_clicked()
    assert len(view.queue_tasks_data) >= 1

    # Simuler le passage à l'état en cours
    view._set_running_ui_state(True)
    assert "Arrêter" in view.btn_start_pipeline.text()

    # Simuler la fin du batch
    view._on_batch_finished(1, 0, 5)
    assert "Démarrer" in view.btn_start_pipeline.text()


def test_batch_view_delimit_button_opens_dialog_with_batch_context(qtbot: Any, monkeypatch: Any) -> None:
    """Vérifie que le bouton de délimitation ouvre DocumentDelimitationDialog avec context='batch'."""
    from ankiforge.ui.views.documents_view.dialogs.delimitation_dialog import DocumentDelimitationDialog

    doc = DocumentModel.create(title="Doc Delimit Test.pdf", content_markdown="Page 1", file_type="pdf")
    view = BatchTab(ai_manager=None)
    qtbot.addWidget(view)

    view.doc_picker_btn.set_document(doc)
    assert not view.btn_delimit_doc.isHidden()

    opened_context = []

    def mock_exec(self_dlg: Any) -> int:
        opened_context.append(getattr(self_dlg, "context", None))
        return 0

    monkeypatch.setattr(DocumentDelimitationDialog, "exec", mock_exec)
    view.btn_delimit_doc.click()
    assert len(opened_context) == 1
    assert opened_context[0] == "batch"


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
    view.doc_picker_btn.set_document(doc)

    # Ajout à la queue -> doit créer 2 tâches indépendantes (1 par chunk)
    view._on_add_to_queue_clicked()
    assert len(view.queue_tasks_data) == 2
    assert view.queue_tasks_data[0]["chunk_label"] == "Section 1"
    assert view.queue_tasks_data[1]["chunk_label"] == "Section 2"

    # Mock de l'exécution du DAG
    def fake_orchestrator_run(self_orch: Any) -> None:
        source = self_orch.state.get_variable("source_chunk") or self_orch.state.get_variable("text_source")
        self_orch.state.variables["generated_cards"] = [{"Front": f"Q pour {source}", "Back": f"A pour {source}"}]

    monkeypatch.setattr(PipelineOrchestrator, "run", fake_orchestrator_run)

    # Démarrer le batch
    view._on_start_batch()
    assert view.worker is not None

    with qtbot.waitSignal(view.worker.batch_finished, timeout=5000):
        pass

    # Vérifications après exécution
    assert view.queue_tasks_data[0]["status"] == "Succès"
    assert view.queue_tasks_data[1]["status"] == "Succès"
    assert view.queue_tasks_data[0]["cards_count"] == 1
    assert view.queue_tasks_data[1]["cards_count"] == 1

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

    # Coche le document dans la liste
    for i in range(view.docs_list.count()):
        it = view.docs_list.item(i)
        doc_obj = it.data(Qt.ItemDataRole.UserRole)
        if doc_obj and getattr(doc_obj, "id", None) == doc.id:
            it.setCheckState(Qt.CheckState.Checked)
            break

    # Ajout à la file d'attente
    view._on_add_to_queue_clicked()

    # Vérification que seule la section 'Intro' a été ajoutée à la file d'attente
    assert len(view.queue_tasks_data) == 1
    assert view.queue_tasks_data[0]["chunk_label"] == "Intro"
    assert view.queue_tasks_data[0]["doc_content"] == "Contenu intro"

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
    """Le mode manuel (1 par 1) construit une tâche de file à partir d'un SliceUnit."""
    from ankiforge.services.batch.slicing_service import SlicingService

    doc = DocumentModel.create(
        title="Doc Slice.pdf",
        content="# Intro\n\nTexte introductif suffisamment long pour constituer une tranche d'étude.\n\n# Technique\n\nSecond paragraphe descriptif des méthodes utilisées.",
        file_type="pdf",
    )
    view = BatchTab(ai_manager=None)
    qtbot.addWidget(view)
    view._segment_inspector_doc = doc
    view.current_deck = None
    view.current_model = None

    slice_unit = SlicingService.slice_by_headings(doc.content, min_words=5)[0]
    task = view._slice_to_queue_task(slice_unit)
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
    view._segment_inspector_doc = doc

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


def test_batch_view_auto_slice_dialog_populates_queue(qtbot: Any, monkeypatch: Any, mock_db: Any) -> None:
    """Le découpage auto injecte les tranches configurées dans la file."""
    from ankiforge.services.batch.slicing_service import SliceUnit
    from ankiforge.ui.views.batch_view.dialogs.auto_slice_config_dialog import AutoSliceConfigDialog

    doc = DocumentModel.create(
        title="Doc Auto Slice.pdf",
        content="# Intro\n\nParagraphe introductif substantiel pour la tranche auto.\n\n# Corps\n\nParagraphe de développement avec de la matière pédagogique.",
        file_type="pdf",
    )

    class FakeDlg:
        def exec(self) -> int:
            return 1

        def get_result(self) -> dict[str, Any]:
            unit = SliceUnit(index=0, title="Intro", heading_path="Intro", content="Contenu intro")
            return {"mode": "headings", "slices": [unit]}

    monkeypatch.setattr(AutoSliceConfigDialog, "exec", FakeDlg.exec)
    monkeypatch.setattr(AutoSliceConfigDialog, "get_result", FakeDlg.get_result)

    view = BatchTab(ai_manager=None)
    qtbot.addWidget(view)
    view.refresh_data()
    view._segment_inspector_doc = doc

    view._on_open_auto_slice()
    assert len(view.queue_tasks_data) == 1
    assert view.queue_tasks_data[0]["chunk_label"] == "Intro"


def test_batch_view_wizard_populates_queue(qtbot: Any, monkeypatch: Any, mock_db: Any) -> None:
    """L'assistant wizard injecte les tâches groupées dans la file (staging par défaut)."""
    from ankiforge.ui.views.batch_view.dialogs.batch_slicing_wizard_dialog import BatchSlicingWizardDialog

    doc = DocumentModel.create(title="Doc Wizard.pdf", content="# Intro\n\nContenu introductif riche pour le wizard.", file_type="pdf")

    class FakeWizard:
        def exec(self) -> int:
            return 1

        def get_configured_payloads(self) -> list[dict[str, Any]]:
            return [
                {
                    "doc": doc,
                    "doc_title": "Doc Wizard.pdf — Intro",
                    "doc_content": "Contenu introductif riche pour le wizard.",
                    "source_chunks": [{"content": "Contenu introductif riche pour le wizard."}],
                    "chunk_label": "Intro",
                    "auto_val": False,
                }
            ]

    monkeypatch.setattr(BatchSlicingWizardDialog, "exec", FakeWizard.exec)
    monkeypatch.setattr(BatchSlicingWizardDialog, "get_configured_payloads", FakeWizard.get_configured_payloads)

    view = BatchTab(ai_manager=None)
    qtbot.addWidget(view)
    view.refresh_data()
    view._segment_inspector_doc = doc

    view._on_open_slicing_wizard()
    assert len(view.queue_tasks_data) == 1
    assert view.queue_tasks_data[0]["chunk_label"] == "Intro"
    assert view.queue_tasks_data[0]["auto_val"] is False


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
    assert "error_message" not in view.queue_tasks_data[0]

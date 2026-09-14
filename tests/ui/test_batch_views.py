import json
from typing import Any

from PySide6.QtCore import Qt

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    DocumentChunkModel,
    DocumentModel,
    LLMConfigModel,
    NoteChunkLinkModel,
    NoteTypeModel,
    NoteVersionModel,
    PipelineModel,
    PipelineStepModel,
)
from ankiforge.services.ai.orchestrator import PipelineOrchestrator
from ankiforge.services.workers.batch_worker import BatchTaskPayload, BatchWorker
from ankiforge.ui.views.batch_view import BatchTab


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

    # Vérification des liens de chunks RAG créés
    links = list(NoteChunkLinkModel.select().where(NoteChunkLinkModel.chunk == chunk))
    assert len(links) == 2

    for link in links:
        note = link.note
        # Vérification des cartes enfants
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

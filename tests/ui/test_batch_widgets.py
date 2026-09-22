"""Tests des widgets de l'Atelier de Production (BatchQueueTable, BatchSlicePanel)
et des chemins d'auto-validation du BatchWorker (legacy + scope snapshots)."""

import json
from typing import Any
from unittest.mock import MagicMock

import pytest

from ankiforge.database.models import (
    DocumentModel,
    PipelineModel,
    PipelineStepModel,
)
from ankiforge.services.ai.orchestrator import PipelineOrchestrator
from ankiforge.services.batch.models import (
    BatchGenerationConfig,
    BatchScopeSnapshot,
    BatchSourceBlock,
    BatchTaskSnapshot,
    BatchTaskStatus,
)
from ankiforge.services.workers.batch_worker import BatchTaskPayload, BatchWorker
from ankiforge.ui.components import IconButton
from ankiforge.ui.views.batch_view.widgets import BatchQueueTable, BatchSlicePanel

pytestmark = pytest.mark.ui


# ── BatchQueueTable ──────────────────────────────────────────────────────────


def _task(status: str = "En attente", chunk_label: str = "Section 1") -> dict[str, Any]:
    return {
        "doc_title": "Doc.md",
        "chunk_label": chunk_label,
        "status": status,
        "progress_pct": 0,
        "cards_count": 0,
        "deck_name": "Général",
        "model_name": "Basique",
        "pipeline_name": "Standard",
        "doc_content": "Contenu de la tranche",
    }


def test_batch_queue_table_empty_state(qtbot: Any) -> None:
    widget = BatchQueueTable()
    qtbot.addWidget(widget)
    widget.set_tasks([])
    assert widget.table.rowCount() == 0
    assert widget.table.isHidden()
    assert not widget.queue_empty.isHidden()
    widget.set_tasks([_task()])
    assert not widget.table.isHidden()
    assert widget.queue_empty.isHidden()


def test_batch_queue_table_renders_9_columns(qtbot: Any) -> None:
    widget = BatchQueueTable()
    qtbot.addWidget(widget)
    assert widget.table.columnCount() == 9
    tasks = [_task("En attente"), _task("Succès", "Section 2")]
    widget.set_tasks(tasks)
    assert widget.table.rowCount() == 2
    item0 = widget.table.item(0, 2)
    assert item0 is not None
    assert item0.text() == "Doc.md › Section 1"


def test_batch_queue_table_filters(qtbot: Any) -> None:
    widget = BatchQueueTable()
    qtbot.addWidget(widget)
    tasks = [_task("En attente"), _task("Succès", "Section 2"), _task("Erreur", "Section 3")]
    widget.set_tasks(tasks)

    widget.set_filter("Erreurs")
    assert widget._status_matches("Erreur")
    assert not widget.table.isRowHidden(2)
    assert widget.table.isRowHidden(0)
    assert widget.table.isRowHidden(1)

    widget.set_filter("Tous")
    assert not widget.table.isRowHidden(0)
    assert not widget.table.isRowHidden(2)


def test_batch_queue_table_sync_completed(qtbot: Any) -> None:
    widget = BatchQueueTable()
    qtbot.addWidget(widget)
    widget.set_tasks([_task("En attente")])
    widget.sync_completed(0, "Succès", 3)
    assert widget.status_badges_map[0].text() == "Succès"
    assert widget.cards_items_map[0].text() == "3 cartes"
    widget.sync_completed(0, "À réviser", 2)
    assert widget.status_badges_map[0].text() == "À réviser"
    assert widget.cards_items_map[0].text() == "2 ⏳"


def test_batch_queue_table_action_signals(qtbot: Any) -> None:
    widget = BatchQueueTable()
    qtbot.addWidget(widget)

    reviews: list[int] = []
    retries: list[int] = []
    removes: list[int] = []
    widget.review_requested.connect(reviews.append)
    widget.retry_requested.connect(retries.append)
    widget.remove_requested.connect(removes.append)

    widget.set_tasks([_task("À réviser"), _task("Erreur", "Section 2")])

    review_cell = widget.table.cellWidget(0, 8)
    retry_cell = widget.table.cellWidget(1, 8)
    assert review_cell is not None and retry_cell is not None

    for btn in review_cell.findChildren(IconButton):
        if "Examiner" in str(btn.toolTip()):
            btn.click()
    for btn in retry_cell.findChildren(IconButton):
        if "Relancer" in str(btn.toolTip()):
            btn.click()
    assert reviews == [0]
    assert retries == [1]

    widget.table.cellWidget(0, 8).findChildren(IconButton)[-1].click()
    assert removes


def test_batch_queue_table_refresh_theme(qtbot: Any) -> None:
    widget = BatchQueueTable()
    qtbot.addWidget(widget)
    widget.set_tasks([_task("En cours")])
    widget.sync_started(0)
    widget.refresh_theme(MagicMock())


# ── BatchSlicePanel ─────────────────────────────────────────────────────────


def _doc_with_headings() -> DocumentModel:
    content = """# Chapitre 1 : Introduction

Un long paragraphe d'introduction qui présente les notions de base indispensables à la compréhension du cours de biologie cellulaire.

# Chapitre 2 : La Membrane

Un second paragraphe décrivant la bicouche lipidique et les protéines transmembranaires responsables du transport des ions.
"""
    return DocumentModel.create(title="Cours Bio.md", content=content, file_type="md")


def test_batch_slice_panel_manual_add(qtbot: Any) -> None:
    doc = _doc_with_headings()
    panel = BatchSlicePanel()
    qtbot.addWidget(panel)
    panel.set_defaults_provider(lambda: {"deck": None, "model": None, "engine": None, "pipeline": None})
    panel.set_document(doc)

    assert panel.btn_add_slice.isEnabled()
    assert panel.slice_combo.count() >= 2

    received: list[list[dict[str, Any]]] = []
    panel.slices_ready.connect(received.append)

    panel.slice_combo.setCurrentIndex(0)
    panel.btn_add_slice.click()

    assert len(received) == 1
    task = received[0][0]
    assert task["doc_title"] == "Cours Bio.md — Chapitre 1 : Introduction"
    assert task["chunk_index"] == 0
    assert "Introduction" in str(task["doc_content"])
    assert task["source_chunks"][0]["content"] == task["doc_content"]
    assert task["status"] == "En attente"


def test_batch_slice_panel_modes_switch_stack(qtbot: Any) -> None:
    panel = BatchSlicePanel()
    qtbot.addWidget(panel)
    assert panel.rb_manual.isChecked()
    assert panel.stack.currentIndex() == 0

    panel.rb_auto.setChecked(True)
    assert panel.stack.currentIndex() == 1
    panel.rb_wizard.setChecked(True)
    assert panel.stack.currentIndex() == 2
    panel.rb_manual.setChecked(True)
    assert panel.stack.currentIndex() == 0


def test_batch_slice_panel_auto_and_wizard_signals(qtbot: Any) -> None:
    doc = _doc_with_headings()
    panel = BatchSlicePanel()
    qtbot.addWidget(panel)
    panel.set_document(doc)

    autos: list[bool] = []
    wizards: list[bool] = []
    panel.auto_slice_requested.connect(lambda: autos.append(True))
    panel.wizard_requested.connect(lambda: wizards.append(True))

    panel.btn_open_auto.click()
    panel.btn_open_wizard.click()
    assert autos
    assert wizards


def test_batch_slice_panel_manual_disabled_without_doc(qtbot: Any) -> None:
    panel = BatchSlicePanel()
    qtbot.addWidget(panel)
    assert not panel.btn_add_slice.isEnabled()
    assert not panel.btn_open_auto.isEnabled()


# ── BatchWorker : chemins d'auto-validation ─────────────────────────────────


def _legacy_task(auto_validation: bool) -> BatchTaskPayload:
    return BatchTaskPayload(
        task_index=0,
        doc_id=1,
        doc_title="Doc Auto.md",
        doc_content="Contenu à transformer en cartes mémoire.",
        deck_id=1,
        deck_name="Général",
        model_id=1,
        model_name="Basique",
        note_type_fields=["Front", "Back"],
        note_type_templates=[],
        pipeline_id=1,
        pipeline_name="Standard",
        llm_id=1,
        llm_config={"provider": "mock", "model_id": "mock-model", "api_key": ""},
        auto_validation=auto_validation,
        source_chunks=[{"content": "Contenu à transformer en cartes mémoire.", "index": 0}],
    )


def _patch_orchestrator(monkeypatch: Any) -> None:
    def fake_run(self_orch: Any) -> None:
        self_orch.state.variables["generated_cards"] = [{"Front": "Quelle est la capitale ?", "Back": "Paris"}]

    monkeypatch.setattr(PipelineOrchestrator, "run", fake_run)


def test_batch_worker_auto_validation_true_emits_accepted(monkeypatch: Any) -> None:
    _patch_orchestrator(monkeypatch)
    worker = BatchWorker(tasks=[_legacy_task(auto_validation=True)])

    accepted: list[tuple[int, int]] = []
    reviewed: list[tuple[int, list[dict[str, Any]]]] = []
    worker.task_accepted.connect(lambda idx, count: accepted.append((idx, count)))
    worker.task_review_ready.connect(lambda idx, notes: reviewed.append((idx, notes)))

    worker.run()

    assert (0, 1) in accepted
    assert reviewed == []


def test_batch_worker_auto_validation_false_emits_review_ready(monkeypatch: Any) -> None:
    _patch_orchestrator(monkeypatch)
    worker = BatchWorker(tasks=[_legacy_task(auto_validation=False)])

    accepted: list[tuple[int, int]] = []
    reviewed: list[tuple[int, list[dict[str, Any]]]] = []
    worker.task_accepted.connect(lambda idx, count: accepted.append((idx, count)))
    worker.task_review_ready.connect(lambda idx, notes: reviewed.append((idx, notes)))

    worker.run()

    assert accepted == []
    assert len(reviewed) == 1
    assert reviewed[0][0] == 0
    assert len(reviewed[0][1]) == 1


def _scope_task(auto_validation: bool) -> BatchTaskSnapshot:
    PipelineModel.delete().where(PipelineModel.id > 0).execute()
    pipe = PipelineModel.create(name=f"Pipeline Scope {auto_validation}")
    PipelineStepModel.create(pipeline=pipe, step_type="LLM_PROMPT", step_order=1, config_data=json.dumps({"prompt_template": "Test"}))
    block = BatchSourceBlock(kind="section", label="Section 1", content="Contenu du scope sélectionné en sections.", ordinal=0)
    scope = BatchScopeSnapshot(
        document_id=1,
        document_title="Doc Scope.pdf",
        selection_mode="sections",
        scope_title="Portée : Section 1",
        blocks=(block,),
    )
    config = BatchGenerationConfig(
        pipeline_id=pipe.id,
        pipeline_name=pipe.name,
        llm_id=1,
        llm_config={"provider": "mock", "model_id": "mock-model", "api_key": ""},
        deck_id=1,
        deck_name="Général",
        model_id=1,
        model_name="Basique",
        note_type_fields=("Front", "Back"),
        note_type_templates=(),
        auto_validation=auto_validation,
    )
    return BatchTaskSnapshot.create(scope, config)


def test_batch_worker_scope_auto_validation_true(monkeypatch: Any) -> None:
    _patch_orchestrator(monkeypatch)
    task = _scope_task(auto_validation=True)
    worker = BatchWorker(tasks=[task])

    accepted: list[tuple[int, int]] = []
    reviewed: list[str] = []
    worker.task_accepted.connect(lambda idx, count: accepted.append((idx, count)))
    worker.task_review_ready.connect(lambda _idx, _notes: reviewed.append("review"))

    worker.run()

    assert task.status == BatchTaskStatus.ACCEPTED
    assert accepted == [(0, 1)]
    assert reviewed == []


def test_batch_worker_scope_auto_validation_false(monkeypatch: Any) -> None:
    _patch_orchestrator(monkeypatch)
    task = _scope_task(auto_validation=False)
    worker = BatchWorker(tasks=[task])

    accepted: list[tuple[int, int]] = []
    reviewed: list[tuple[int, list[dict[str, Any]]]] = []
    worker.task_accepted.connect(lambda idx, count: accepted.append((idx, count)))
    worker.task_review_ready.connect(lambda idx, notes: reviewed.append((idx, notes)))

    worker.run()

    assert task.status == BatchTaskStatus.REVIEW
    assert accepted == []
    assert len(reviewed) == 1
    assert len(reviewed[0][1]) == 1

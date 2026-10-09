"""Tests des widgets de l'Atelier de Production (BatchQueueTable)
et des chemins d'auto-validation du BatchWorker (legacy + scope snapshots)."""

import json
from typing import Any
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QAbstractItemView

from ankiforge.database.models import (
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
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.views.batch_view.widgets import BatchQueueTable

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


def test_batch_queue_table_uses_extended_selection(qtbot: Any) -> None:
    widget = BatchQueueTable()
    qtbot.addWidget(widget)
    assert widget.table.selectionMode() == QAbstractItemView.SelectionMode.ExtendedSelection


def test_batch_queue_table_context_menu_selection_follows_click(qtbot: Any, monkeypatch: Any) -> None:
    widget = BatchQueueTable()
    qtbot.addWidget(widget)
    widget.set_tasks([_task("En attente", "S1"), _task("Succès", "S2"), _task("Erreur", "S3")])

    emitted: list[tuple[int, QPoint]] = []
    widget.context_menu_requested.connect(lambda row, pos: emitted.append((row, pos)))

    widget.table.selectRow(2)
    monkeypatch.setattr(widget.table, "rowAt", lambda _y: 0)
    widget._on_context_menu_requested(QPoint(10, 10))

    assert emitted and emitted[0][0] == 0
    assert isinstance(emitted[0][1], QPoint)
    assert widget.selected_rows() == [0]


def test_batch_queue_table_context_menu_keeps_multi_selection(qtbot: Any, monkeypatch: Any) -> None:
    widget = BatchQueueTable()
    qtbot.addWidget(widget)
    widget.set_tasks([_task("En attente", "S1"), _task("En attente", "S2"), _task("En attente", "S3")])

    widget.table.selectRow(0)
    widget.table.selectionModel().select(
        widget.table.model().index(1, 0),
        widget.table.selectionModel().SelectionFlag.Select | widget.table.selectionModel().SelectionFlag.Rows,
    )
    assert widget.selected_rows() == [0, 1]

    emitted: list[int] = []
    widget.context_menu_requested.connect(lambda row, pos: emitted.append(row))
    monkeypatch.setattr(widget.table, "rowAt", lambda _y: 0)
    widget._on_context_menu_requested(QPoint(10, 10))

    assert emitted == [0]
    assert widget.selected_rows() == [0, 1]


def test_batch_queue_table_context_menu_empty_zone_reports_minus_one(qtbot: Any, monkeypatch: Any) -> None:
    widget = BatchQueueTable()
    qtbot.addWidget(widget)
    widget.set_tasks([_task()])

    emitted: list[int] = []
    widget.context_menu_requested.connect(lambda row, pos: emitted.append(row))
    monkeypatch.setattr(widget.table, "rowAt", lambda _y: -1)
    widget._on_context_menu_requested(QPoint(10, 10))

    assert emitted == [-1]


def test_batch_queue_table_row_appearance_terminal_and_rejected(qtbot: Any) -> None:
    widget = BatchQueueTable()
    qtbot.addWidget(widget)
    widget.set_tasks(
        [
            _task("Succès", "S1"),
            _task("Acceptée", "S2"),
            _task("Partielle", "S3"),
            _task("Annulé", "S4"),
            _task("Rejetée", "S5"),
            _task("Erreur", "S6"),
            _task("En attente", "S7"),
        ]
    )

    muted_hex = QColor(DesignTokens.TEXT_MUTED).name()
    for row in range(4):
        item = widget.table.item(row, 2)
        assert item is not None
        assert item.foreground().color().name() == muted_hex
        assert item.font().strikeOut() is False

    rejected = widget.table.item(4, 2)
    assert rejected is not None
    assert rejected.font().strikeOut() is True
    assert rejected.foreground().color().name() != muted_hex

    error_item = widget.table.item(5, 2)
    assert error_item is not None
    assert error_item.font().strikeOut() is False
    assert error_item.foreground().color().name() != muted_hex

    pending_item = widget.table.item(6, 2)
    assert pending_item is not None
    assert pending_item.font().strikeOut() is False
    assert pending_item.foreground().color().name() != muted_hex


def test_batch_queue_table_sync_completed_applies_row_appearance(qtbot: Any) -> None:
    widget = BatchQueueTable()
    qtbot.addWidget(widget)
    widget.set_tasks([_task("En attente")])

    muted_hex = QColor(DesignTokens.TEXT_MUTED).name()
    assert widget.table.item(0, 2).foreground().color().name() != muted_hex

    widget.sync_completed(0, "Succès", 3)
    assert widget.status_badges_map[0].text() == "Succès"
    assert widget.table.item(0, 2).foreground().color().name() == muted_hex

    widget.sync_completed(0, "Rejetée", 0)
    assert widget.table.item(0, 2).font().strikeOut() is True


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

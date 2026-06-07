# ruff: noqa: E501
import json
import logging
import uuid
from typing import Any, cast

import qtawesome as qta
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import (
    CardModel,
    db,
    DeckModel,
    DocumentModel,
    FolderModel,
    LLMConfigModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionModel,
    PipelineModel,
    PipelineStepModel,
)
from ankiforge.services.ai.pricing_service import calculate_job_estimate
from ankiforge.services.workers.batch_worker import BatchWorker, BatchTaskPayload
from ankiforge.ui.components.components import ActionButton, DangerButton, DBComboBox, PrimaryButton, RoundedPanel
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.anki_renderer import get_max_cloze_index
from ankiforge.utils.vision_utils import count_images

logger = logging.getLogger(__name__)


class BatchTab(QWidget):
    """
    Card Factory View (Batch Processing).
    Allows the user to select multiple documents, configure a pipeline
    for each, and launch background card generation.
    """

    def __init__(self, ai_manager: Any) -> None:
        """
        Initializes the automation tab.

        Args:
            ai_manager (AIManager): Centralized AI services manager.
        """
        super().__init__()
        self.worker: BatchWorker | None = None
        self.ai_manager = ai_manager
        self.chunk_strategies = [
            self.tr("Semantic (Headings)"),
            self.tr("Overlap"),
            self.tr("Classic"),
            self.tr("None (Entire document)"),
        ]

        self._setup_ui()
        self._connect_signals()
        self._setup_shortcuts()

        self.refresh_data()

    def _setup_ui(self) -> None:
        """Builds and organizes layouts and main widgets."""
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(20, 20, 20, 20)
        self.main_layout.setSpacing(20)

        self._build_header()

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.setHandleWidth(10)
        self.main_splitter.setChildrenCollapsible(False)

        self._build_source_panel()
        self._build_right_panels()

        self.main_splitter.setSizes([250, 950])
        self.main_layout.addWidget(self.main_splitter)

    def _build_header(self) -> None:
        """Builds the view header."""
        titles_layout = QVBoxLayout()
        titles_layout.setSpacing(2)

        header = QLabel(self.tr("⚙️ Advanced Automation (Card Factory)"))
        header.setStyleSheet("font-size: 15px; font-weight: bold; color: palette(text);")
        header.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)

        subtitle = QLabel(self.tr("Manage your queue and customize processing for each document."))
        subtitle.setStyleSheet("color: palette(placeholder-text); font-size: 11px;")
        subtitle.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)

        titles_layout.addWidget(header)
        titles_layout.addWidget(subtitle)
        self.main_layout.addLayout(titles_layout)

    def _build_source_panel(self) -> None:
        """Builds the source documents selection panel (left)."""
        source_panel = RoundedPanel()
        source_layout = QVBoxLayout(source_panel)
        source_layout.setContentsMargins(15, 15, 15, 15)

        lbl_source = QLabel(self.tr("1. SOURCE (COURSES AND FOLDERS)"))
        lbl_source.setStyleSheet("font-weight: bold; color: palette(placeholder-text); font-size: 11px; letter-spacing: 1px; margin-bottom: 5px;")
        source_layout.addWidget(lbl_source)

        self.tree_source = QTreeWidget()
        self.tree_source.setHeaderHidden(True)
        self.tree_source.setFrameShape(QFrame.Shape.NoFrame)
        self.tree_source.viewport().setAutoFillBackground(False)
        self.tree_source.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        source_layout.addWidget(self.tree_source)

        self.btn_add_to_queue = ActionButton("fa5s.arrow-right", self.tr(" Add to Queue"))
        source_layout.addWidget(self.btn_add_to_queue)

        source_panel.setMinimumWidth(150)
        self.main_splitter.addWidget(source_panel)

    def _build_right_panels(self) -> None:
        """Builds the right zone split between queue and console."""
        self.right_splitter = QSplitter(Qt.Orientation.Vertical)
        self.right_splitter.setHandleWidth(10)

        self._build_queue_panel()
        self._build_console_panel()

        self.right_splitter.setSizes([350, 300])
        self.right_splitter.setMinimumWidth(300)
        self.main_splitter.addWidget(self.right_splitter)

    def _build_queue_panel(self) -> None:
        """Builds the default configuration panel and queue table."""
        queue_panel = RoundedPanel()
        queue_layout = QVBoxLayout(queue_panel)
        queue_layout.setContentsMargins(15, 15, 15, 15)

        lbl_config = QLabel(self.tr("DEFAULT CONFIGURATION"))
        lbl_config.setStyleSheet("font-weight: bold; color: palette(placeholder-text); font-size: 11px; letter-spacing: 1px; margin-bottom: 5px;")
        queue_layout.addWidget(lbl_config)

        default_params_layout = QGridLayout()

        self.default_deck = DBComboBox(DeckModel)
        self.default_deck.setMinimumWidth(80)
        self.default_model = DBComboBox(NoteTypeModel)
        self.default_model.setMinimumWidth(80)
        self.default_llm = DBComboBox(LLMConfigModel, display_field="display_name", sort_field="display_name")
        self.default_llm.setMinimumWidth(80)
        self.default_pipeline = DBComboBox(PipelineModel)
        self.default_pipeline.setMinimumWidth(80)
        self.default_chunking = QComboBox()
        self.default_chunking.setMinimumWidth(80)
        self.default_chunking.addItems(self.chunk_strategies)
        self.default_vision = QCheckBox(self.tr("👁️ Vision"))
        self.default_vision.setChecked(False)

        default_params_layout.addWidget(QLabel(self.tr("Deck:")), 0, 0)
        default_params_layout.addWidget(QLabel(self.tr("Model:")), 0, 1)
        default_params_layout.addWidget(QLabel(self.tr("Engine:")), 0, 2)
        default_params_layout.addWidget(QLabel(self.tr("AI Pipeline:")), 0, 3)
        default_params_layout.addWidget(QLabel(self.tr("Chunking:")), 0, 4)
        default_params_layout.addWidget(QLabel(self.tr("Option:")), 0, 5)

        default_params_layout.addWidget(self.default_deck, 1, 0)
        default_params_layout.addWidget(self.default_model, 1, 1)
        default_params_layout.addWidget(self.default_llm, 1, 2)
        default_params_layout.addWidget(self.default_pipeline, 1, 3)
        default_params_layout.addWidget(self.default_chunking, 1, 4)
        default_params_layout.addWidget(self.default_vision, 1, 5)

        queue_layout.addLayout(default_params_layout)

        lbl_queue = QLabel(self.tr("2. QUEUE"))
        lbl_queue.setStyleSheet("font-weight: bold; color: palette(placeholder-text); font-size: 11px; letter-spacing: 1px; margin-top: 15px; margin-bottom: 5px;")
        queue_layout.addWidget(lbl_queue)

        self.table_queue = QTableWidget()
        self.table_queue.setFrameShape(QFrame.Shape.NoFrame)
        self.table_queue.setColumnCount(8)
        self.table_queue.setHorizontalHeaderLabels(
            [self.tr("Document"), self.tr("Deck"), self.tr("Model"), self.tr("AI Engine"), self.tr("AI Pipeline"), self.tr("Chunking"), self.tr("Vision"), self.tr("Action")]
        )
        self.table_queue.horizontalHeader().setStretchLastSection(False)
        self.table_queue.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in range(1, 8):
            self.table_queue.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        self.table_queue.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table_queue.setAlternatingRowColors(True)
        self.table_queue.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table_queue.verticalHeader().setVisible(False)

        self.lbl_empty_queue = QLabel(self.tr("The queue is empty. Select documents on the left to start."))
        self.lbl_empty_queue.setStyleSheet("color: palette(placeholder-text); font-style: italic;")
        self.lbl_empty_queue.setAlignment(Qt.AlignmentFlag.AlignCenter)

        queue_layout.addWidget(self.lbl_empty_queue)
        queue_layout.addWidget(self.table_queue)

        self.right_splitter.addWidget(queue_panel)

    def _build_console_panel(self) -> None:
        """Builds the bottom panel displaying logs, estimate, and progress bar."""
        console_panel = RoundedPanel()
        console_layout = QVBoxLayout(console_panel)
        console_layout.setContentsMargins(15, 15, 15, 15)

        lbl_console = QLabel(self.tr("MONITORING CONSOLE"))
        lbl_console.setStyleSheet("font-weight: bold; color: palette(placeholder-text); font-size: 11px; letter-spacing: 1px; margin-bottom: 5px;")
        console_layout.addWidget(lbl_console)

        self.console_log = QTextEdit()
        self.console_log.setReadOnly(True)
        self.console_log.setFrameShape(QFrame.Shape.NoFrame)
        self.console_log.viewport().setAutoFillBackground(False)
        font = QFont("Consolas")
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.console_log.setFont(font)
        console_layout.addWidget(self.console_log)

        self.lbl_estimate = QLabel(self.tr("📊 Estimate: 0 tokens | 💰 Cost: Free"))
        self.lbl_estimate.setStyleSheet(
            "font-weight: bold; color: palette(highlight); font-size: 13px; margin-top: 10px; margin-bottom: 10px; padding: 10px; border: 1px dashed palette(highlight); border-radius: 6px;"
        )
        self.lbl_estimate.setAlignment(Qt.AlignmentFlag.AlignCenter)
        console_layout.addWidget(self.lbl_estimate)

        self.lbl_disclaimer = QLabel(
            self.tr(
                "<i>* <b>Calculation method</b> : 1 token ≈ 4 characters. Generation creates about 20% of original volume. "
                "Overlap chunking adds a 15% surcharge.<br>"
                "⚠️ <b>Warning</b> : These values are purely estimates. AnkiForge declines all responsibility for actual costs billed by API providers.</i>"
            )
        )
        self.lbl_disclaimer.setStyleSheet("color: palette(placeholder-text); font-size: 10px;")
        self.lbl_disclaimer.setWordWrap(True)
        console_layout.addWidget(self.lbl_disclaimer)

        bottom_layout = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(14)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.progress_bar.setStyleSheet("""
            QProgressBar { border: none; background-color: palette(base); border-radius: 4px; }
            QProgressBar::chunk { background-color: palette(highlight); border-radius: 4px; }
        """)
        bottom_layout.addWidget(self.progress_bar)

        self.lbl_status = QLabel(self.tr("Ready."))
        self.lbl_status.setStyleSheet("color: palette(placeholder-text); font-size: 12px; margin-left: 10px; margin-right: 10px;")
        bottom_layout.addWidget(self.progress_bar)
        bottom_layout.addWidget(self.lbl_status)

        self.btn_start = PrimaryButton(qta.icon("fa5s.rocket", color="white"), self.tr(" Start the Factory"))
        self.btn_start.setMinimumWidth(200)
        bottom_layout.addWidget(self.btn_start)

        self.btn_cancel = DangerButton(qta.icon("fa5s.stop", color="white"), self.tr(" Cancel processing"))
        self.btn_cancel.setMinimumWidth(200)
        self.btn_cancel.hide()
        bottom_layout.addWidget(self.btn_cancel)

        console_layout.addLayout(bottom_layout)
        self.right_splitter.addWidget(console_panel)

    def _connect_signals(self) -> None:
        """Connects UI signals to associated slots."""
        self.btn_add_to_queue.clicked.connect(self.add_selected_to_queue)
        self.btn_start.clicked.connect(self.start_batch)
        self.btn_cancel.clicked.connect(self.cancel_batch)

    def _setup_shortcuts(self) -> None:
        """Initializes view keyboard shortcuts."""
        self.shortcut_start = QShortcut(QKeySequence("Ctrl+Return"), self)
        self.shortcut_start.activated.connect(self.start_batch)

        self.shortcut_remove_queue = QShortcut(QKeySequence.StandardKey.Delete, self.table_queue)
        self.shortcut_remove_queue.activated.connect(self._remove_selected_from_table)

    @Slot()
    def refresh_data(self) -> None:
        """MainWindow contract: Refreshes lists and folders."""
        self.default_deck.refresh_data()
        self.default_model.refresh_data()
        self.default_llm.refresh_data()
        self.default_pipeline.refresh_data()
        self.load_tree_source()

    @Slot()
    def load_tree_source(self) -> None:
        self.tree_source.clear()
        folders = FolderModel.select().order_by(FolderModel.name)
        for folder in folders:
            folder_item = QTreeWidgetItem(self.tree_source, [f" {folder.name}"])
            folder_item.setIcon(0, qta.icon("fa5s.folder", color="#FFC107"))
            folder_item.setData(0, Qt.ItemDataRole.UserRole, {"type": "folder", "id": folder.id})

            docs = DocumentModel.select().where(DocumentModel.folder == folder).order_by(DocumentModel.title)
            for doc in docs:
                doc_item = QTreeWidgetItem(folder_item, [f" {doc.title}"])
                doc_item.setIcon(0, qta.icon("fa5s.file-alt", color="#90CAF9"))
                doc_item.setData(0, Qt.ItemDataRole.UserRole, {"type": "doc", "id": doc.id, "title": doc.title})

        orphan_docs = DocumentModel.select().where(DocumentModel.folder.is_null()).order_by(DocumentModel.title)
        orphan_root = QTreeWidgetItem(self.tree_source, [self.tr(" Unclassified")])
        orphan_root.setIcon(0, qta.icon("fa5s.box-open", color="#B0BEC5"))
        for doc in orphan_docs:
            doc_item = QTreeWidgetItem(orphan_root, [f" {doc.title}"])
            doc_item.setIcon(0, qta.icon("fa5s.file-alt", color="#90CAF9"))
            doc_item.setData(0, Qt.ItemDataRole.UserRole, {"type": "doc", "id": doc.id, "title": doc.title})

        self.tree_source.expandAll()

    @Slot()
    def add_selected_to_queue(self) -> None:
        selected_items = self.tree_source.selectedItems()
        if not selected_items:
            return

        docs_to_add = []
        for item in selected_items:
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if not data:
                continue

            if data.get("type") == "doc":
                docs_to_add.append(data)
            elif data.get("type") == "folder" and data.get("id") is not None:
                folder_docs = DocumentModel.select().where(DocumentModel.folder_id == data["id"])
                for d in folder_docs:
                    docs_to_add.append({"id": d.id, "title": d.title})

        for doc_data in docs_to_add:
            self._add_row_to_queue(doc_data["id"], doc_data["title"])

        self._check_ready_state()

    def _add_row_to_queue(self, doc_id: int, title: str) -> None:
        row_idx = self.table_queue.rowCount()
        self.table_queue.insertRow(row_idx)

        # 1. Document
        item_doc = QTableWidgetItem(f"📄 {title}")
        item_doc.setData(Qt.ItemDataRole.UserRole, doc_id)
        self.table_queue.setItem(row_idx, 0, item_doc)

        # 2. Deck
        cb_deck = QComboBox()
        for i in range(self.default_deck.count()):
            cb_deck.addItem(self.default_deck.itemText(i), self.default_deck.itemData(i))
        cb_deck.setCurrentIndex(self.default_deck.currentIndex())
        self.table_queue.setCellWidget(row_idx, 1, cb_deck)

        # 3. Card Model
        cb_model = QComboBox()
        for i in range(self.default_model.count()):
            cb_model.addItem(self.default_model.itemText(i), self.default_model.itemData(i))
        cb_model.setCurrentIndex(self.default_model.currentIndex())
        self.table_queue.setCellWidget(row_idx, 2, cb_model)

        # 4. AI Engine
        cb_llm = QComboBox()
        for i in range(self.default_llm.count()):
            cb_llm.addItem(self.default_llm.itemText(i), self.default_llm.itemData(i))
        cb_llm.setCurrentIndex(self.default_llm.currentIndex())
        self.table_queue.setCellWidget(row_idx, 3, cb_llm)

        # 5. Pipeline
        cb_pipe = QComboBox()
        for i in range(self.default_pipeline.count()):
            cb_pipe.addItem(self.default_pipeline.itemText(i), self.default_pipeline.itemData(i))
        cb_pipe.setCurrentIndex(self.default_pipeline.currentIndex())
        self.table_queue.setCellWidget(row_idx, 4, cb_pipe)

        # 6. Chunking
        cb_chunk = QComboBox()
        cb_chunk.addItems(self.chunk_strategies)
        cb_chunk.setCurrentIndex(self.default_chunking.currentIndex())
        self.table_queue.setCellWidget(row_idx, 5, cb_chunk)

        # 7. Vision
        cb_vision = QCheckBox(self.tr("Enable"))
        cb_vision.setChecked(self.default_vision.isChecked())
        self.table_queue.setCellWidget(row_idx, 6, cb_vision)

        # 8. Action

        btn_remove = DangerButton(qta.icon("fa5s.times", color="white"), "")
        btn_remove.clicked.connect(lambda _, r=row_idx: self._remove_row(r))
        self.table_queue.setCellWidget(row_idx, 7, btn_remove)

        cb_llm.currentIndexChanged.connect(self._update_estimates)
        cb_pipe.currentIndexChanged.connect(self._update_estimates)
        cb_chunk.currentIndexChanged.connect(self._update_estimates)

        cb_llm.currentIndexChanged.connect(self._update_estimates)
        cb_pipe.currentIndexChanged.connect(self._update_estimates)
        cb_vision.stateChanged.connect(self._update_estimates)

        self.table_queue.resizeRowToContents(row_idx)

    def _remove_row(self, row_idx: int) -> None:
        self.table_queue.removeRow(row_idx)
        for r in range(row_idx, self.table_queue.rowCount()):
            btn = cast(QPushButton, self.table_queue.cellWidget(r, 7))
            btn.clicked.disconnect()
            btn.clicked.connect(lambda _, current_r=r: self._remove_row(current_r))
        self._check_ready_state()

    def _check_ready_state(self) -> None:
        count = self.table_queue.rowCount()
        self.btn_start.setEnabled(count > 0)
        self.lbl_status.setText(self.tr("{0} document(s) in queue.").format(count))
        self.lbl_empty_queue.setVisible(count == 0)
        self.table_queue.setVisible(count > 0)
        self._update_estimates()

    @Slot(str)
    def append_log(self, text: str) -> None:
        self.console_log.append(text)
        scrollbar = self.console_log.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    @Slot()
    def start_batch(self) -> None:
        if self.table_queue.rowCount() == 0:
            return

        tasks_payloads = []
        for row in range(self.table_queue.rowCount()):
            item_doc = self.table_queue.item(row, 0)
            doc_id = item_doc.data(Qt.ItemDataRole.UserRole) if item_doc is not None else None

            cb_deck = cast(QComboBox, self.table_queue.cellWidget(row, 1))
            cb_model = cast(QComboBox, self.table_queue.cellWidget(row, 2))
            cb_llm = cast(QComboBox, self.table_queue.cellWidget(row, 3))
            cb_pipe = cast(QComboBox, self.table_queue.cellWidget(row, 4))
            cb_chunk = cast(QComboBox, self.table_queue.cellWidget(row, 5))
            cb_vision = cast(QCheckBox, self.table_queue.cellWidget(row, 6))

            deck_id = cb_deck.currentData()
            model_id = cb_model.currentData()
            llm_id = cb_llm.currentData()
            pipe_id = cb_pipe.currentData()
            chunk_strategy = cb_chunk.currentText()

            if not doc_id or not deck_id or not model_id or not pipe_id or not llm_id:
                logger.warning(f"Incomplete configuration at row {row + 1} of batch table.")
                show_toast(self, self.tr("Incomplete configuration at row {0}.").format(row + 1), is_error=True)
                return

            # DATA RETRIEVAL ON MAIN THREAD
            doc = DocumentModel.get_by_id(doc_id)
            note_type = NoteTypeModel.get_by_id(model_id)
            pipeline = PipelineModel.get_by_id(pipe_id)
            llm_config_model = LLMConfigModel.get_by_id(llm_id)

            steps_data = []
            for step in pipeline.steps.order_by(PipelineStepModel.step_order):
                steps_data.append({"name": step.agent.name, "system_prompt": step.agent.system_prompt, "output_format": getattr(step.agent, "output_format", "json")})

            payload = BatchTaskPayload(
                doc_id=int(doc_id),
                doc_title=doc.title,
                doc_content=doc.content,
                deck_id=deck_id,
                model_id=model_id,
                note_type_fields=json.loads(note_type.fields_schema) if note_type.fields_schema else ["Front", "Back"],
                note_type_templates=json.loads(note_type.templates) if note_type.templates else [],
                pipeline_id=pipe_id,
                pipeline_steps=steps_data,
                llm_id=llm_id,
                llm_config={
                    "display_name": llm_config_model.display_name,
                    "model_id": llm_config_model.model_id,
                    "context_limit": llm_config_model.context_limit,
                    "api_key": llm_config_model.api_key,
                    "provider": llm_config_model.provider,
                },
                chunk_strategy=chunk_strategy,
                use_vision=cb_vision.isChecked(),
            )
            tasks_payloads.append(payload)

        self.btn_start.hide()
        self.btn_cancel.show()
        self.btn_cancel.setEnabled(True)

        self.btn_add_to_queue.setEnabled(False)
        self.table_queue.setEnabled(False)
        self.console_log.clear()
        self.progress_bar.setValue(0)

        logger.info(f"Launching card factory: {len(tasks_payloads)} document(s) to process.")
        self.append_log(self.tr("🚀 Launching the Factory: {0} document(s) to process.").format(len(tasks_payloads)))

        self.worker = BatchWorker(ai_provider=self.ai_manager.provider, tasks=tasks_payloads)
        self.worker.batch_data_ready.connect(self.save_extracted_notes_to_db)
        self.worker.progress_val.connect(self.progress_bar.setValue)
        self.worker.progress_text.connect(self.lbl_status.setText)
        self.worker.log.connect(self.append_log)
        self.worker.finished.connect(self.on_batch_finished)
        self.worker.error.connect(self.on_batch_error)
        self.worker.cancelled.connect(self.on_batch_cancelled)

        self.worker.start()

    @Slot()
    def cancel_batch(self) -> None:
        """Requests a clean stop of the worker."""
        if self.worker is not None and self.worker.isRunning():
            self.worker.cancel()
            self.btn_cancel.setEnabled(False)
            self.btn_cancel.setText(self.tr(" Stopping..."))
            logger.info("Batch processing cancellation request received.")
            self.lbl_status.setText(self.tr("Cancellation requested, waiting for stop..."))
            self.append_log(self.tr("⏳ Stop request sent. Waiting for current cycle to finish..."))

    @Slot(list, int, int)
    def save_extracted_notes_to_db(self, notes_data: list[dict[str, Any]], deck_id: int, model_id: int) -> None:
        """
        Saves notes extracted by BatchWorker to the database.
        Runs on main thread to guarantee Peewee thread-safety.
        """
        try:
            deck = DeckModel.get_by_id(deck_id)
            note_type = NoteTypeModel.get_by_id(model_id)
            templates = json.loads(note_type.templates) if note_type.templates else []
            is_cloze = any("{{cloze:" in t.get("qfmt", "") or "{{cloze:" in t.get("afmt", "") for t in templates)

            with db.atomic():
                for cleaned_note_fields in notes_data:
                    note = NoteModel.create(
                        guid=str(uuid.uuid4())[:10],
                        note_type=note_type,
                        tags=json.dumps(["AnkiForge_Batch"]),
                        status="pending",
                    )
                    NoteVersionModel.create(
                        note=note,
                        version_number=1,
                        content=json.dumps(cleaned_note_fields, ensure_ascii=False),
                        source="ai_batch",
                        is_active=True,
                    )

                    if is_cloze:
                        max_cloze = get_max_cloze_index(cleaned_note_fields)
                        num_cards = max(1, max_cloze)
                        for i in range(num_cards):
                            CardModel.create(note=note, deck=deck, template_index=i)
                    else:
                        for idx, _ in enumerate(templates):
                            CardModel.create(note=note, deck=deck, template_index=idx)

            logger.info(f"Thread-safe saving of {len(notes_data)} notes successful.")
        except Exception as e:
            logger.exception("Error while saving notes thread-safely")
            self.append_log(self.tr("❌ CRITICAL SAVE ERROR: {0}").format(str(e)))

    @Slot(int, int)
    def on_batch_finished(self, success_count: int, error_count: int) -> None:
        self._unlock_ui()
        self.lbl_status.setText(self.tr("Done."))
        msg = self.tr("Queue processing finished.\n\n✅ Successful documents: {0}\n❌ Failed documents: {1}").format(success_count, error_count)
        self.append_log(f"\n{'=' * 40}\n{msg}")
        (show_toast(self, self.tr("Batch processing finished!")))

    @Slot(str)
    def on_batch_error(self, error_msg: str) -> None:
        self._unlock_ui()
        self.lbl_status.setText(self.tr("Fatal error."))
        QMessageBox.critical(self, self.tr("Fatal Error"), error_msg)

    @Slot()
    def on_batch_cancelled(self) -> None:
        """Handles the UI once the worker has actually stopped."""
        self._unlock_ui()
        logger.info("Batch processing cancelled properly.")
        self.lbl_status.setText(self.tr("Processing cancelled."))
        show_toast(self, self.tr("Operation was cancelled properly."), is_error=True)

    def _unlock_ui(self) -> None:
        """Restores the UI."""
        self.btn_cancel.hide()
        self.btn_cancel.setText(self.tr(" Cancel processing"))
        self.btn_start.show()
        self.btn_start.setEnabled(True)
        self.btn_add_to_queue.setEnabled(True)
        self.table_queue.setEnabled(True)

    @Slot()
    def _remove_selected_from_table(self) -> None:
        """Removes the currently selected row from the queue table."""
        current_row = self.table_queue.currentRow()
        if current_row != -1:
            self._remove_row(current_row)

    @Slot()
    def _update_estimates(self) -> None:
        """Calculates token and cost estimates for the queue."""
        total_tokens = 0
        total_cost = 0.0

        for row in range(self.table_queue.rowCount()):
            try:
                item_doc = self.table_queue.item(row, 0)
                doc_id = item_doc.data(Qt.ItemDataRole.UserRole) if item_doc is not None else None

                cb_llm = cast(QComboBox, self.table_queue.cellWidget(row, 3))
                cb_pipe = cast(QComboBox, self.table_queue.cellWidget(row, 4))
                cb_chunk = cast(QComboBox, self.table_queue.cellWidget(row, 5))

                llm_id = cb_llm.currentData()
                pipe_id = cb_pipe.currentData()
                chunk_strategy = cb_chunk.currentText()

                if not doc_id or not llm_id or not pipe_id:
                    continue

                doc = DocumentModel.get_by_id(doc_id)
                llm = LLMConfigModel.get_by_id(llm_id)
                pipe = PipelineModel.get_by_id(pipe_id)

                # Calcul des images pour la majoration vision
                img_count = 0
                cb_vision = cast(QCheckBox, self.table_queue.cellWidget(row, 6))
                if cb_vision.isChecked():
                    img_count = count_images(doc.content)

                # Appel à la logique métier centralisée
                row_tokens, row_cost = calculate_job_estimate(
                    text_length=len(doc.content),
                    step_count=max(1, pipe.steps.count()),
                    chunk_strategy=chunk_strategy,
                    use_vision=cb_vision.isChecked(),
                    image_count=img_count,
                    prompt_pricing=llm.prompt_pricing,
                    completion_pricing=llm.completion_pricing,
                )

                total_tokens += row_tokens
                total_cost += row_cost
            except (AttributeError, TypeError, ValueError, Exception):
                continue

        # Visual update
        if total_tokens == 0:
            self.lbl_estimate.setText(self.tr("📊 Estimate: 0 tokens | 💰 Cost: Free"))
            self.lbl_estimate.setStyleSheet(
                "font-weight: bold; color: palette(placeholder-text); font-size: 13px; margin-top: 10px; margin-bottom: 5px; padding: 10px; border: 1px dashed palette(alternate-base); border-radius: 6px;"
            )
        elif total_cost > 0.001:
            self.lbl_estimate.setText(self.tr("📊 Estimate: ~{0} tokens | 💰 API Cost: ~${1:.3f}").format(total_tokens, total_cost).replace(",", " "))
            self.lbl_estimate.setStyleSheet("font-weight: bold; color: #FF9800; font-size: 13px; margin-top: 10px; margin-bottom: 5px; padding: 10px; border: 1px dashed #FF9800; border-radius: 6px;")
        else:
            cost_str = self.tr("Free (Local / Free API)")
            self.lbl_estimate.setText(self.tr("📊 Estimate: ~{0} tokens | 💰 Cost: {1}").format(total_tokens, cost_str).replace(",", " "))
            self.lbl_estimate.setStyleSheet("font-weight: bold; color: #4CAF50; font-size: 13px; margin-top: 10px; margin-bottom: 5px; padding: 10px; border: 1px dashed #4CAF50; border-radius: 6px;")

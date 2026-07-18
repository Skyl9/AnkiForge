# ruff: noqa: E501
import json
import logging
from typing import Any

import qtawesome as qta
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import (
    DeckModel,
    DocumentModel,
    LLMConfigModel,
    NoteTypeModel,
    PipelineModel,
    PipelineStepModel,
)
from ankiforge.services.cards.note_manager import NoteManager
from ankiforge.services.workers.creation_worker import CreationWorker, CreationTaskPayload
from ankiforge.ui.components.components import ActionButton, DangerButton, PrimaryButton, RoundedPanel, DBComboBox
from ankiforge.ui.widgets.card_preview_widget import CardPreviewWidget
from ankiforge.ui.widgets.highlighters import SourceHighlighter
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.vision_utils import count_images

logger = logging.getLogger(__name__)


class CreationTab(QWidget):
    """
    Manual Anki card creation interface assisted by AI.
    Allows targeting a specific source text and transforming it into structured notes.
    """

    def __init__(self, ai_manager: Any) -> None:
        """
        Initializes the card creation tab.

        Args:
            ai_manager (AIManager): Centralized AI services manager.
        """
        super().__init__()
        self.ai_manager = ai_manager
        self.worker_thread: CreationWorker | None = None
        self.generated_notes: list[dict[str, str]] = []

        self._setup_ui()
        self._connect_signals()
        self._setup_shortcuts()

        self.load_documents()

    def _setup_ui(self) -> None:
        """Initializes and organizes main graphical components in 3 columns."""
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(20, 20, 20, 20)
        self.main_layout.setSpacing(0)

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.setHandleWidth(8)
        self.main_splitter.setChildrenCollapsible(False)

        config_panel = self._build_config_section()
        source_panel = self._build_source_section()
        results_panel = self._build_results_section()

        self.main_splitter.addWidget(config_panel)
        self.main_splitter.addWidget(source_panel)
        self.main_splitter.addWidget(results_panel)

        self.main_splitter.setSizes([280, 400, 600])
        self.main_layout.addWidget(self.main_splitter)

    def _build_config_section(self) -> QWidget:
        """Builds the left panel containing AI parameters and targets."""
        params_panel = RoundedPanel()
        params_layout = QVBoxLayout(params_panel)
        params_layout.setContentsMargins(15, 15, 15, 15)
        params_layout.setSpacing(15)

        lbl_title_1 = QLabel(self.tr("1. CONFIGURATION"))
        lbl_title_1.setStyleSheet("font-weight: bold; color: palette(placeholder-text); font-size: 11px; letter-spacing: 1px;")
        params_layout.addWidget(lbl_title_1)

        lbl_style = "color: palette(text); font-size: 12px; font-weight: bold;"

        lbl_pipeline = QLabel(self.tr("Generation pipeline:"))
        lbl_pipeline.setStyleSheet(lbl_style)
        self.pipeline_selector = DBComboBox(PipelineModel)

        lbl_engine = QLabel(self.tr("AI Engine:"))
        lbl_engine.setStyleSheet(lbl_style)
        self.llm_selector = DBComboBox(LLMConfigModel, display_field="display_name", sort_field="display_name")

        lbl_deck = QLabel(self.tr("Destination deck:"))
        lbl_deck.setStyleSheet(lbl_style)
        self.deck_selector = DBComboBox(DeckModel)

        lbl_model = QLabel(self.tr("Note model (Anki):"))
        lbl_model.setStyleSheet(lbl_style)
        self.model_selector = DBComboBox(NoteTypeModel)

        params_layout.addWidget(lbl_pipeline)
        params_layout.addWidget(self.pipeline_selector)
        params_layout.addWidget(lbl_engine)
        params_layout.addWidget(self.llm_selector)
        params_layout.addWidget(lbl_deck)
        params_layout.addWidget(self.deck_selector)
        params_layout.addWidget(lbl_model)
        params_layout.addWidget(self.model_selector)

        self.cb_vision = QCheckBox(self.tr("👁️ Enable image analysis"))
        self.cb_vision.setStyleSheet("color: palette(highlight); font-weight: bold; margin-top: 10px;")
        self.cb_vision.setChecked(False)
        params_layout.addWidget(self.cb_vision)

        params_layout.addStretch()

        return params_panel

    def _build_source_section(self) -> QWidget:
        """Builds the central area for source text input and selection."""
        source_panel = RoundedPanel()
        source_layout = QVBoxLayout(source_panel)
        source_layout.setContentsMargins(15, 15, 15, 15)
        source_layout.setSpacing(10)

        lbl_title_2 = QLabel(self.tr("2. SOURCE TEXT"))
        lbl_title_2.setStyleSheet("font-weight: bold; color: palette(placeholder-text); font-size: 11px; letter-spacing: 1px;")
        source_layout.addWidget(lbl_title_2)

        source_header = QHBoxLayout()
        self.doc_selector = QComboBox()
        self.doc_selector.setMinimumWidth(100)
        source_header.addWidget(self.doc_selector, stretch=1)

        self.btn_refresh_docs = ActionButton("fa5s.sync", "")
        source_header.addWidget(self.btn_refresh_docs)
        source_layout.addLayout(source_header)

        self.section_selector = QComboBox()
        self.section_selector.setMinimumWidth(100)
        source_layout.addWidget(self.section_selector)

        self.source_text = QTextEdit()
        self.source_text.setPlaceholderText(self.tr("Select a document then a section..."))
        self.source_highlighter = SourceHighlighter(self.source_text.document())
        source_layout.addWidget(self.source_text)

        self.token_label = QLabel(self.tr("Tokens: 0 / ?"))
        self.token_label.setStyleSheet("color: palette(placeholder-text); font-size: 12px;")
        source_layout.addWidget(self.token_label)

        self.token_bar = QProgressBar()
        self.token_bar.setTextVisible(False)
        self.token_bar.setFixedHeight(6)
        source_layout.addWidget(self.token_bar)

        self.lbl_progress = QLabel("")
        self.lbl_progress.setStyleSheet("color: #4CAF50; font-weight: bold; font-size: 12px;")
        source_layout.addWidget(self.lbl_progress)

        self.btn_generate = PrimaryButton(qta.icon("fa5s.magic", color="white"), self.tr(" Generate Cards"))
        source_layout.addWidget(self.btn_generate)

        self.btn_cancel = DangerButton(qta.icon("fa5s.stop", color="white"), self.tr(" Cancel"))
        self.btn_cancel.hide()
        source_layout.addWidget(self.btn_cancel)

        return source_panel

    def _build_results_section(self) -> QWidget:
        """Builds the right area displaying the results table and previews."""
        results_panel = RoundedPanel()
        results_layout = QVBoxLayout(results_panel)
        results_layout.setContentsMargins(15, 15, 15, 15)
        results_layout.setSpacing(10)

        lbl_title_3 = QLabel(self.tr("3. RESULTS & PREVIEW"))
        lbl_title_3.setStyleSheet("font-weight: bold; color: palette(placeholder-text); font-size: 11px; letter-spacing: 1px;")
        results_layout.addWidget(lbl_title_3)

        results_splitter = QSplitter(Qt.Orientation.Vertical)
        results_splitter.setHandleWidth(8)
        results_splitter.setChildrenCollapsible(False)

        # Top: Table
        table_container = QWidget()
        table_layout = QVBoxLayout(table_container)
        table_layout.setContentsMargins(0, 0, 0, 0)

        self.results_table = QTableWidget()
        self.results_table.horizontalHeader().setStretchLastSection(True)
        self.results_table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked)
        self.results_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.results_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.results_table.setAlternatingRowColors(True)
        self.results_table.setFrameShape(QFrame.Shape.NoFrame)
        table_layout.addWidget(self.results_table)

        # Bottom: Preview / Console
        bottom_container = QWidget()
        bottom_layout = QVBoxLayout(bottom_container)
        bottom_layout.setContentsMargins(0, 0, 0, 0)

        right_tabs = QTabWidget()
        right_tabs.setStyleSheet("""
            QTabWidget::pane { border: none; border-top: 1px solid palette(alternate-base); }
            QTabBar::tab { background: transparent; color: palette(text); padding: 8px 15px; margin-right: 2px; border-radius: 4px; }
            QTabBar::tab:selected { background: palette(alternate-base); font-weight: bold; }
            QTabBar::tab:hover:!selected { background: palette(window); }
        """)

        self.preview_widget = CardPreviewWidget(show_header=False)
        right_tabs.addTab(self.preview_widget, qta.icon("fa5s.eye"), self.tr(" Preview"))

        self.console_log = QTextEdit()
        self.console_log.setReadOnly(True)
        self.console_log.setFrameShape(QFrame.Shape.NoFrame)
        font = QFont("Consolas")
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.console_log.setFont(font)
        right_tabs.addTab(self.console_log, qta.icon("fa5s.terminal"), self.tr(" AI Console"))

        bottom_layout.addWidget(right_tabs)

        self.btn_save = PrimaryButton(qta.icon("fa5s.save", color="white"), self.tr(" Save to database"))
        self.btn_save.setEnabled(False)
        self.btn_save.setStyleSheet("""
                    PrimaryButton { background-color: #2196F3; color: white; border-radius: 6px; padding: 10px 20px; font-weight: bold; }
                    PrimaryButton:hover { background-color: #1976D2; }
                    PrimaryButton:disabled { background-color: rgba(33, 150, 243, 0.3); color: rgba(255, 255, 255, 0.5); border: 1px dashed rgba(33, 150, 243, 0.5); }
                """)
        bottom_layout.addWidget(self.btn_save)

        results_splitter.addWidget(table_container)
        results_splitter.addWidget(bottom_container)
        results_splitter.setSizes([400, 300])

        results_layout.addWidget(results_splitter)

        return results_panel

    def _connect_signals(self) -> None:
        """Connects UI signals to associated slots."""
        self.model_selector.currentIndexChanged.connect(self.on_model_changed)
        self.llm_selector.currentIndexChanged.connect(self.update_token_estimate)
        self.cb_vision.stateChanged.connect(self.update_token_estimate)
        self.doc_selector.currentIndexChanged.connect(self.on_document_changed)
        self.btn_refresh_docs.clicked.connect(self.load_documents)
        self.section_selector.currentIndexChanged.connect(self.on_section_changed)
        self.source_text.textChanged.connect(self.update_token_estimate)

        self.btn_generate.clicked.connect(self.start_generation)
        self.btn_cancel.clicked.connect(self.cancel_generation)

        self.results_table.itemChanged.connect(self.on_table_item_changed)
        self.results_table.itemSelectionChanged.connect(self.update_preview)
        self.btn_save.clicked.connect(self.save_to_database)

    def _setup_shortcuts(self) -> None:
        """Configures view keyboard shortcuts."""
        self.shortcut_generate = QShortcut(QKeySequence("Ctrl+Return"), self)
        self.shortcut_generate.activated.connect(self.start_generation)
        self.shortcut_save_db = QShortcut(QKeySequence("Ctrl+S"), self)
        self.shortcut_save_db.activated.connect(self.save_to_database)

    def is_dirty(self) -> bool:
        """Indique si des notes générées attendent d'être sauvegardées."""
        return len(self.generated_notes) > 0

    def reset_unsaved_state(self) -> None:
        """Réinitialise l'état de l'onglet après l'abandon explicite des données par l'utilisateur."""
        self.generated_notes.clear()
        self.results_table.setRowCount(0)
        self.preview_widget.clear_memory()

        self.btn_save.setEnabled(False)
        self.btn_generate.setText(self.tr(" Generate Cards"))
        self.btn_generate.setEnabled(True)
        self.btn_cancel.hide()

        logger.info("État de la vue Création réinitialisé (données jetées).")

    @Slot()
    def refresh_data(self) -> None:
        """Standardized method called by MainWindow on tab change."""
        self.deck_selector.refresh_data()
        self.model_selector.refresh_data()
        self.llm_selector.refresh_data()
        self.pipeline_selector.refresh_data()
        self.load_documents()
        self.on_model_changed()

    @Slot()
    def update_token_estimate(self) -> None:
        text = self.source_text.toPlainText()
        estimated_tokens = len(text) // 4

        if self.cb_vision.isChecked():
            img_count = count_images(text)
            if img_count > 0:
                estimated_tokens += img_count * 300  # 300 token surcharge per image

        llm_id = self.llm_selector.currentData()
        max_tokens = 8192
        if llm_id:
            try:
                max_tokens = LLMConfigModel.get_by_id(llm_id).context_limit
            except (ValueError, AttributeError):
                pass

        self.token_bar.setMaximum(max_tokens)
        self.token_bar.setValue(min(estimated_tokens, max_tokens))
        self.token_label.setText(self.tr("<b>Tokens: ~{0} / {1}</b>").format(estimated_tokens, max_tokens).replace(",", " "))

        if estimated_tokens < (max_tokens * 0.5):
            color = "#4CAF50"
            self.btn_generate.setText(self.tr(" Generate Cards"))
        elif estimated_tokens < (max_tokens * 0.8):
            color = "#FF9800"
            self.btn_generate.setText(self.tr("Generate Cards (Long text)"))
        else:
            color = "#F44336"
            self.btn_generate.setText(self.tr("Generate (AI Overflow Risk!)"))

        self.token_label.setStyleSheet(f"color: {color};")
        self.token_bar.setStyleSheet(f"""
                QProgressBar {{ border: 1px solid palette(alternate-base); border-radius: 4px; background-color: palette(base); }}
                QProgressBar::chunk {{ background-color: {color}; border-radius: 4px; }}
            """)

    @Slot()
    def load_documents(self) -> None:
        """Loads document list from database."""
        self.doc_selector.blockSignals(True)
        self.doc_selector.clear()
        self.doc_selector.addItem(self.tr("-- Select a document --"), None)

        for doc in DocumentModel.select().order_by(DocumentModel.created_at.desc()):
            self.doc_selector.addItem(doc.title, doc.id)

        self.doc_selector.blockSignals(False)

        if self.doc_selector.count() > 1:
            self.doc_selector.setCurrentIndex(1)

    @staticmethod
    def _parse_markdown_sections(text: str) -> list[tuple[str, str]]:
        sections = []
        current_title = ""
        current_content: list[str] = []
        in_code_block = False

        for line in text.split("\n"):
            if line.strip().startswith("```"):
                in_code_block = not in_code_block

            if not in_code_block and line.startswith("#"):
                if current_title or current_content:
                    if "".join(current_content).strip():
                        sections.append((current_title if current_title else "Introduction", "\n".join(current_content)))

                clean_title = line.replace("#", "").strip()
                if len(clean_title) > 50:
                    clean_title = clean_title[:47] + "..."
                current_title = clean_title
                current_content = [line]
            else:
                current_content.append(line)

        if current_content and "".join(current_content).strip():
            sections.append((current_title if current_title else "Text", "\n".join(current_content)))

        return sections

    @Slot(int)
    def on_document_changed(self, index: int) -> None:
        doc_id = self.doc_selector.itemData(index)
        self.section_selector.blockSignals(True)
        self.section_selector.clear()

        if doc_id:
            doc = DocumentModel.get_by_id(doc_id)
            full_text = doc.content

            sections = self._parse_markdown_sections(full_text)
            self.section_selector.addItem(self.tr("📑 All document"), full_text)
            for title, content in sections:
                self.section_selector.addItem(self.tr("🔹 {0}").format(title), content)

            self.source_text.setPlainText(full_text)
        else:
            self.source_text.clear()

        self.section_selector.blockSignals(False)

    @Slot(int)
    def on_section_changed(self, index: int) -> None:
        if index >= 0:
            content = self.section_selector.itemData(index)
            self.source_text.setPlainText(content)

    @Slot()
    def on_model_changed(self) -> None:
        model_id = self.model_selector.currentData()
        if not model_id:
            return

        note_type = NoteTypeModel.get_by_id(model_id)
        fields = json.loads(note_type.fields_schema) if note_type.fields_schema else []

        self.results_table.blockSignals(True)
        self.results_table.clear()
        self.results_table.setColumnCount(len(fields))
        self.results_table.setHorizontalHeaderLabels(fields)
        self.results_table.setRowCount(0)
        self.results_table.blockSignals(False)

        self.update_preview()

    @Slot()
    def start_generation(self) -> None:
        text = self.source_text.toPlainText()
        model_id = self.model_selector.currentData()
        pipeline_id = self.pipeline_selector.currentData()
        llm_id = self.llm_selector.currentData()

        if not text.strip():
            logger.warning("Attempted generation without source text.")
            show_toast(self, self.tr("Please enter source text."), is_error=True)
            return
        if not pipeline_id:
            logger.warning("Attempted generation without selected pipeline.")
            show_toast(self, self.tr("Please select an AI Pipeline."), is_error=True)
            return
        if not llm_id:
            logger.warning("Attempted generation without selected engine.")
            show_toast(self, self.tr("Please select an AI engine."), is_error=True)
            return

        # DATA PREPARATION ON MAIN THREAD
        note_type = NoteTypeModel.get_by_id(model_id)
        pipeline = PipelineModel.get_by_id(pipeline_id)
        llm_config = LLMConfigModel.get_by_id(llm_id)
        active_provider = self.ai_manager.create_provider_from_config(llm_config)

        steps_data = []
        for step in pipeline.steps.order_by(PipelineStepModel.step_order):
            steps_data.append({"name": step.agent.name, "system_prompt": step.agent.system_prompt, "output_format": getattr(step.agent, "output_format", "json")})

        payload = CreationTaskPayload(
            text_source=text,
            note_type_id=model_id,
            note_type_fields_schema=note_type.fields_schema,
            pipeline_id=pipeline_id,
            pipeline_name=pipeline.name,
            pipeline_steps=steps_data,
            use_vision=self.cb_vision.isChecked(),
        )

        self.btn_generate.hide()
        self.btn_cancel.show()
        self.btn_cancel.setEnabled(True)

        self.btn_generate.setEnabled(False)
        self.results_table.setRowCount(0)
        self.preview_widget.clear_memory()
        self.console_log.clear()

        logger.info(f"Launching AI generation (Pipeline: {pipeline.name}, LLM: {llm_config.display_name}, Vision: {payload.use_vision}).")
        self.worker_thread = CreationWorker(active_provider, payload)
        self.worker_thread.progress.connect(self.update_progress)
        self.worker_thread.log.connect(self.append_log)
        self.worker_thread.finished.connect(self.on_generation_success)
        self.worker_thread.error.connect(self.on_generation_error)
        self.worker_thread.cancelled.connect(self.on_generation_cancelled)
        self.worker_thread.start()

    @Slot()
    def cancel_generation(self) -> None:
        if self.worker_thread is not None and self.worker_thread.isRunning():
            self.worker_thread.cancel()
            self.btn_cancel.setEnabled(False)
            self.btn_cancel.setText(self.tr(" Stopping..."))
            logger.info("AI generation stop request received.")
            self.append_log(self.tr("\n AI stop request..."))

    @Slot(str)
    def append_log(self, text: str) -> None:
        self.console_log.append(text)

    @Slot(str)
    def update_progress(self, message: str) -> None:
        self.btn_generate.setText(message)

    @Slot(list)
    def on_generation_success(self, generated_notes: list[dict[str, str]]) -> None:
        self.generated_notes = generated_notes
        self.btn_generate.setEnabled(True)
        self.btn_generate.setText(self.tr(" Regenerate Cards"))
        self.btn_save.setEnabled(True)

        self.btn_cancel.hide()
        self.btn_generate.show()
        self.btn_generate.setEnabled(True)
        self.btn_generate.setText(self.tr(" Regenerate Cards"))
        self.btn_save.setEnabled(True)

        model_id = self.model_selector.currentData()
        note_type = NoteTypeModel.get_by_id(model_id)
        fields = json.loads(note_type.fields_schema)

        self.results_table.blockSignals(True)
        self.results_table.setRowCount(len(generated_notes))
        for row, note_dict in enumerate(generated_notes):
            for col, field_name in enumerate(fields):
                val = note_dict.get(field_name, "")
                if isinstance(val, list):
                    val = "<br>".join([str(item) for item in val])
                elif not isinstance(val, str):
                    val = str(val) if val is not None else ""

                note_dict[field_name] = val
                self.results_table.setItem(row, col, QTableWidgetItem(val))
        self.results_table.blockSignals(False)

        if len(generated_notes) > 0:
            self.results_table.selectRow(0)

    @Slot(str)
    def on_generation_error(self, error_msg: str) -> None:
        self.btn_cancel.hide()
        self.btn_generate.show()

        self.btn_generate.setEnabled(True)
        self.btn_generate.setText(self.tr(" Generate Cards"))
        QMessageBox.critical(self, self.tr("AI Error"), error_msg)

    @Slot(QTableWidgetItem)
    def on_table_item_changed(self, item: QTableWidgetItem) -> None:
        row = item.row()
        col = item.column()
        header_item = self.results_table.horizontalHeaderItem(col)
        if header_item is None:
            return
        field_name = header_item.text()

        if 0 <= row < len(self.generated_notes):
            self.generated_notes[row][field_name] = item.text()
            selected_items = self.results_table.selectedItems()
            if selected_items and selected_items[0].row() == row:
                self.update_preview()

    @Slot()
    def update_preview(self) -> None:
        selected_items = self.results_table.selectedItems()
        if not selected_items or not self.generated_notes:
            self.preview_widget.set_empty_state(self.tr("Select a row in the table<br>to preview the card."))
            return

        row = selected_items[0].row()
        if row >= len(self.generated_notes):
            return

        current_data = self.generated_notes[row]
        model_id = self.model_selector.currentData()
        note_type = NoteTypeModel.get_by_id(model_id)

        self.preview_widget.update_preview(note_type, current_data)

    @Slot()
    def save_to_database(self) -> None:
        if not self.generated_notes:
            return

        deck_id = self.deck_selector.currentData()
        model_id = self.model_selector.currentData()

        deck = DeckModel.get_by_id(deck_id)
        note_type = NoteTypeModel.get_by_id(model_id)

        try:
            for note_data in self.generated_notes:
                NoteManager.create_note(note_type=note_type, deck=deck, content_dict=note_data, tags=["AnkiForge_AI"], status="new", source="ai")

            logger.info(f"Created and saved {len(self.generated_notes)} notes to database.")
            show_toast(self, self.tr("{0} notes created!").format(len(self.generated_notes)))

            self.generated_notes.clear()
            self.results_table.setRowCount(0)
            self.preview_widget.clear_memory()
            self.btn_save.setEnabled(False)

        except Exception as e:
            logger.exception("Unable to save generated notes to database")
            QMessageBox.critical(self, self.tr("Database Error"), self.tr("Unable to save: {0}").format(str(e)))

    @Slot()
    def on_generation_cancelled(self) -> None:
        self.btn_cancel.hide()
        self.btn_cancel.setText(self.tr(" Cancel"))
        self.btn_generate.show()
        self.btn_generate.setEnabled(True)
        self.btn_generate.setText(self.tr(" Generate Cards"))
        logger.info("AI generation cancelled by user.")
        show_toast(self, self.tr("Generation cancelled."), is_error=True)

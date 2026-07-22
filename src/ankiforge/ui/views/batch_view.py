"""
Vue Batch Factory (CI/CD Power User) — 100% Conforme à la Maquette concept_ide.
- Panneau de sélection des documents sources à gauche.
- Configuration par défaut et File d'attente (Queue Table) en haut à droite.
- Console de suivi Terminal CI/CD (#0c0c0c, texte vert #10b981) avec bouton 'Démarrer l'Usine'.
- Traitement massif asynchrone via BatchWorker avec sauvegarde atomique Peewee.
"""

import json
import logging
import uuid
from typing import Any, Optional

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QSplitter,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    DocumentModel,
    LLMConfigModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionModel,
    PipelineModel,
    PipelineStepModel,
    db,
)
from ankiforge.services.workers.batch_worker import BatchTaskPayload, BatchWorker
from ankiforge.ui.components import (
    Badge,
    DangerButton,
    IconButton,
    IdePanel,
    PrimaryButton,
    SecondaryButton,
    StyledComboBox,
    StyledLineEdit,
    StyledTableWidget,
    StyledTextEdit,
)
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.anki_renderer import get_max_cloze_index
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class BatchView(QWidget):
    """
    Batch Factory CI/CD View — 100% Conforme à la Maquette concept_ide.
    """

    def __init__(self, ai_manager: Optional[Any] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.ai_manager = ai_manager
        self.worker: Optional[BatchWorker] = None
        self.queue_tasks_data: list[dict[str, Any]] = []

        self._setup_ui()
        self._connect_signals()
        self.refresh_data()

    def _setup_ui(self) -> None:
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(self.main_splitter)

        # --- COLONNE GAUCHE : 1. Source (Cours) ---
        self.source_panel = IdePanel(detachable=True)
        self.source_panel.setMinimumWidth(260)

        source_content = QWidget()
        source_layout = QVBoxLayout(source_content)
        source_layout.setContentsMargins(12, 12, 12, 12)
        source_layout.setSpacing(10)

        lbl_source_title = QLabel("DOCUMENTS DISPONIBLES")
        lbl_source_title.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        source_layout.addWidget(lbl_source_title)

        self.doc_list = QListWidget()
        self.doc_list.setStyleSheet(f"""
            QListWidget {{
                background-color: #1a1d24;
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                color: {DesignTokens.TEXT_PRIMARY};
            }}
            QListWidget::item {{
                padding: 8px;
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
            }}
            QListWidget::item:selected {{
                background-color: {DesignTokens.BG_HOVER};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
        """)
        source_layout.addWidget(self.doc_list, 1)

        self.btn_add_to_queue = SecondaryButton("Ajouter à la file")
        self.btn_add_to_queue.setIcon(load_phosphor_icon("ph.arrow-right", color=DesignTokens.TEXT_PRIMARY))
        self.btn_add_to_queue.clicked.connect(self._on_add_selected_to_queue)
        source_layout.addWidget(self.btn_add_to_queue)

        self.source_panel.add_tab("1. Source (Cours)", source_content, "ph.folder", closable=False)
        self.main_splitter.addWidget(self.source_panel)

        # --- COLONNE DROITE : Config, File d'attente & Terminal Console ---
        self.right_splitter = QSplitter(Qt.Orientation.Vertical)
        self.main_splitter.addWidget(self.right_splitter)

        # Panel HAUT : Config par défaut & File d'attente
        self.queue_panel = IdePanel(detachable=True)
        queue_content = QWidget()
        queue_layout = QVBoxLayout(queue_content)
        queue_layout.setContentsMargins(12, 12, 12, 12)
        queue_layout.setSpacing(12)

        # Config par défaut (Form Row)
        lbl_cfg_title = QLabel("CONFIGURATION PAR DÉFAUT DES NOUVELLES TÂCHES")
        lbl_cfg_title.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        queue_layout.addWidget(lbl_cfg_title)

        config_row = QHBoxLayout()
        config_row.setSpacing(8)

        def add_cfg_field(layout: QHBoxLayout, label_text: str, widget: QWidget, flex: int = 1) -> None:
            group = QVBoxLayout()
            lbl = QLabel(label_text)
            lbl.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px; font-weight: bold;")
            group.addWidget(lbl)
            group.addWidget(widget)
            layout.addLayout(group, flex)

        self.pkg_input = StyledLineEdit()
        self.pkg_input.setText("Général")
        add_cfg_field(config_row, "Paquet :", self.pkg_input, 1)

        self.model_combo = StyledComboBox()
        add_cfg_field(config_row, "Modèle :", self.model_combo, 1)

        self.engine_combo = StyledComboBox()
        add_cfg_field(config_row, "Moteur :", self.engine_combo, 1)

        self.pipeline_combo = StyledComboBox()
        add_cfg_field(config_row, "Pipeline :", self.pipeline_combo, 2)

        self.chunk_combo = StyledComboBox()
        self.chunk_combo.addItems(["Sémantique (Titres)", "Par paragraphe", "Par 1000 mots"])
        add_cfg_field(config_row, "Découpage :", self.chunk_combo, 1)

        self.vision_cb = QCheckBox("Vision")
        self.vision_cb.setIcon(load_phosphor_icon("ph.eye", color="#eab308"))
        self.vision_cb.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11px; margin-top: 16px;")
        config_row.addWidget(self.vision_cb)

        queue_layout.addLayout(config_row)

        # File d'attente (Table)
        lbl_queue_title = QLabel("2. FILE D'ATTENTE")
        lbl_queue_title.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px; margin-top: 6px;")
        queue_layout.addWidget(lbl_queue_title)

        self.queue_table = StyledTableWidget(["Document", "Paquet", "Modèle", "Moteur IA", "Pipeline IA", "Découpage", "Vision", "Action"])
        self.queue_table.setSelectionBehavior(StyledTableWidget.SelectionBehavior.SelectRows)
        queue_layout.addWidget(self.queue_table, 1)

        self.queue_panel.add_tab("Configuration et File d'attente", queue_content, "ph.gear", closable=False)
        self.right_splitter.addWidget(self.queue_panel)

        # Panel BAS : Terminal Console de Suivi
        self.terminal_panel = IdePanel(detachable=True)

        terminal_content = QWidget()
        terminal_layout = QVBoxLayout(terminal_content)
        terminal_layout.setContentsMargins(0, 0, 0, 0)
        terminal_layout.setSpacing(0)

        # Console de logs (#0c0c0c)
        self.console_output = StyledTextEdit()
        self.console_output.setReadOnly(True)
        self.console_output.setStyleSheet("""
            QPlainTextEdit {
                background-color: #0c0c0c;
                color: #10b981;
                font-family: 'JetBrains Mono', 'Fira Code', monospace;
                font-size: 12px;
                line-height: 1.5;
                padding: 12px;
                border: none;
            }
        """)
        terminal_layout.addWidget(self.console_output, 1)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #1a1d24;
                border: none;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #10b981, stop:1 #3b82f6);
            }
        """)
        terminal_layout.addWidget(self.progress_bar)

        # Toolbar inférieure (Metrics & Démarrer l'Usine)
        terminal_footer = QWidget()
        terminal_footer.setStyleSheet("background-color: #111318; border-top: 1px solid #232730; padding: 8px 12px;")
        footer_layout = QHBoxLayout(terminal_footer)
        footer_layout.setContentsMargins(12, 6, 12, 6)

        self.lbl_estimates = QLabel("📊 Estimation : 0 tokens | 💰 Coût : Gratuit")
        self.lbl_estimates.setStyleSheet(f"color: {DesignTokens.COLOR_BLUE}; font-family: {DesignTokens.FONT_CODE}; font-size: 11px; font-weight: bold;")
        footer_layout.addWidget(self.lbl_estimates)

        footer_layout.addStretch()

        self.lbl_status_badge = Badge("READY", variant="outline", color=DesignTokens.COLOR_GREEN)
        footer_layout.addWidget(self.lbl_status_badge)

        self.btn_start = PrimaryButton("Démarrer l'Usine")
        self.btn_start.setIcon(load_phosphor_icon("ph.rocket-launch", color="white"))
        self.btn_start.setStyleSheet("""
            QPushButton {
                background-color: #10b981;
                color: white;
                font-weight: bold;
                border-radius: 6px;
                padding: 8px 18px;
                border: none;
            }
            QPushButton:hover {
                background-color: #059669;
            }
        """)
        self.btn_start.clicked.connect(self._on_start_batch)
        footer_layout.addWidget(self.btn_start)

        self.btn_cancel = DangerButton("Arrêter l'Usine", ghost=True)
        self.btn_cancel.setIcon(load_phosphor_icon("ph.stop-circle", color=DesignTokens.COLOR_RED))
        self.btn_cancel.hide()
        self.btn_cancel.clicked.connect(self._on_cancel_batch)
        footer_layout.addWidget(self.btn_cancel)

        terminal_layout.addWidget(terminal_footer)

        self.terminal_panel.add_tab("root@ankiforge:~/console_de_suivi", terminal_content, "ph.terminal", closable=False)
        self.right_splitter.addWidget(self.terminal_panel)

        self.right_splitter.setSizes([350, 220])
        self.main_splitter.setSizes([260, 800])

        self._log_terminal("> Initializing AnkiForge CI/CD Engine... OK")
        self._log_terminal("> Waiting for tasks...")

    def _connect_signals(self) -> None:
        pass

    def refresh_data(self) -> None:
        """Recharge les données dynamiques depuis Peewee."""
        try:
            # Documents source
            self.doc_list.clear()
            docs = list(DocumentModel.select())
            if docs:
                for doc in docs:
                    item = QListWidgetItem(f"📄 {doc.title}")
                    item.setData(Qt.ItemDataRole.UserRole, doc)
                    self.doc_list.addItem(item)
            else:
                item = QListWidgetItem("Aucun document disponible")
                item.setFlags(Qt.ItemFlag.NoItemFlags)
                self.doc_list.addItem(item)

            # Combos de config par défaut
            self.model_combo.blockSignals(True)
            self.model_combo.clear()
            for nt in NoteTypeModel.select():
                self.model_combo.addItem(nt.name, userData=nt)
            self.model_combo.blockSignals(False)

            self.engine_combo.blockSignals(True)
            self.engine_combo.clear()
            for eg in LLMConfigModel.select():
                self.engine_combo.addItem(eg.name, userData=eg)
            self.engine_combo.blockSignals(False)

            self.pipeline_combo.blockSignals(True)
            self.pipeline_combo.clear()
            for pipe in PipelineModel.select():
                self.pipeline_combo.addItem(pipe.name, userData=pipe)
            self.pipeline_combo.blockSignals(False)

            decks = list(DeckModel.select())
            if decks:
                self.pkg_input.setText(decks[0].name)

        except Exception as e:
            logger.warning("Erreur refresh_data batch_view: %s", e)

    def is_dirty(self) -> bool:
        return len(self.queue_tasks_data) > 0

    def _log_terminal(self, text: str) -> None:
        self.console_output.appendPlainText(text)

    @Slot()
    def _on_add_selected_to_queue(self) -> None:
        selected_item = self.doc_list.currentItem()
        if not selected_item:
            show_toast(self, "Veuillez sélectionner un document à ajouter.", is_error=True)
            return

        doc: Optional[DocumentModel] = selected_item.data(Qt.ItemDataRole.UserRole)
        if not doc:
            return

        selected_nt = self.model_combo.currentData()
        selected_engine = self.engine_combo.currentData()
        selected_pipeline = self.pipeline_combo.currentData()

        task_data = {
            "doc": doc,
            "deck_name": self.pkg_input.text().strip() or "Général",
            "note_type": selected_nt,
            "engine": selected_engine,
            "pipeline": selected_pipeline,
            "chunk_strategy": self.chunk_combo.currentText(),
            "use_vision": self.vision_cb.isChecked(),
        }

        self.queue_tasks_data.append(task_data)
        self._update_queue_table()
        self._update_estimates()
        show_toast(self, f"Document '{doc.title}' ajouté à la file d'attente.")

    def _update_queue_table(self) -> None:
        self.queue_table.blockSignals(True)
        self.queue_table.setRowCount(len(self.queue_tasks_data))

        for i, task in enumerate(self.queue_tasks_data):
            doc: DocumentModel = task["doc"]
            deck_name: str = task["deck_name"]
            nt = task["note_type"]
            engine = task["engine"]
            pipeline = task["pipeline"]
            chunk = task["chunk_strategy"]
            use_vision = task["use_vision"]

            self.queue_table.setItem(i, 0, QTableWidgetItem(doc.title))
            self.queue_table.setItem(i, 1, QTableWidgetItem(deck_name))
            self.queue_table.setItem(i, 2, QTableWidgetItem(nt.name if nt else "Basique"))
            self.queue_table.setItem(i, 3, QTableWidgetItem(engine.name if engine else "Défaut"))
            self.queue_table.setItem(i, 4, QTableWidgetItem(pipeline.name if pipeline else "Standard"))
            self.queue_table.setItem(i, 5, QTableWidgetItem(chunk))

            vis_item = QTableWidgetItem("Oui" if use_vision else "Non")
            self.queue_table.setItem(i, 6, vis_item)

            # Bouton de suppression de la ligne
            btn_del = IconButton("ph.trash", tooltip="Retirer de la file", size=20)
            btn_del.clicked.connect(lambda _, row_idx=i: self._remove_from_queue(row_idx))

            del_widget = QWidget()
            del_layout = QHBoxLayout(del_widget)
            del_layout.setContentsMargins(4, 0, 4, 0)
            del_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            del_layout.addWidget(btn_del)

            self.queue_table.setCellWidget(i, 7, del_widget)

        self.queue_table.blockSignals(False)

    def _remove_from_queue(self, row_idx: int) -> None:
        if 0 <= row_idx < len(self.queue_tasks_data):
            self.queue_tasks_data.pop(row_idx)
            self._update_queue_table()
            self._update_estimates()

    def _update_estimates(self) -> None:
        total_tokens = 0
        total_words = 0
        for task in self.queue_tasks_data:
            doc: DocumentModel = task["doc"]
            if hasattr(doc, "content") and doc.content:
                words = len(doc.content.split())
                total_words += words
                total_tokens += int(words * 1.3)

        if total_tokens == 0:
            self.lbl_estimates.setText("📊 Estimation : 0 tokens | 💰 Coût : Gratuit")
        else:
            self.lbl_estimates.setText(f"📊 Estimation : ~{total_tokens:,} tokens ({total_words} mots) | 💰 Coût : Inclus")

    @Slot()
    def _on_start_batch(self) -> None:
        if not self.queue_tasks_data:
            show_toast(self, "La file d'attente est vide ! Sélectionnez des documents à gauche.", is_error=True)
            return

        tasks_payloads: list[BatchTaskPayload] = []

        for task in self.queue_tasks_data:
            doc: DocumentModel = task["doc"]
            deck_name: str = task["deck_name"]

            deck, _ = DeckModel.get_or_create(name=deck_name)

            selected_nt = task["note_type"]
            note_type = selected_nt if isinstance(selected_nt, NoteTypeModel) else NoteTypeModel.select().first()
            if not note_type:
                note_type = NoteTypeModel.create(name="Basic", fields_schema='["Front", "Back"]', templates="[]", css_style="")

            selected_pipeline = task["pipeline"]
            pipeline_id = selected_pipeline.id if selected_pipeline and hasattr(selected_pipeline, "id") else 1

            pipeline_steps = []
            if selected_pipeline and hasattr(selected_pipeline, "id"):
                steps = PipelineStepModel.select().where(PipelineStepModel.pipeline == selected_pipeline).order_by(PipelineStepModel.step_order)
                for step in steps:
                    if step.agent:
                        pipeline_steps.append(
                            {
                                "name": step.agent.name,
                                "system_prompt": step.agent.system_prompt,
                                "output_format": getattr(step.agent, "output_format", "json"),
                            }
                        )

            if not pipeline_steps:
                pipeline_steps = [
                    {
                        "name": "BatchGenerator",
                        "system_prompt": 'Génère des cartes Anki sous forme de tableau JSON [{"front": "...", "back": "..."}].',
                        "output_format": "json",
                    }
                ]

            selected_engine = task["engine"]
            llm_id = selected_engine.id if selected_engine and hasattr(selected_engine, "id") else 1
            llm_config = {
                "display_name": selected_engine.name if selected_engine else "LLM",
                "model_id": getattr(selected_engine, "model_id", "default"),
                "context_limit": 128000,
                "api_key": getattr(selected_engine, "api_key", ""),
                "provider": getattr(selected_engine, "provider_type", "openai"),
            }

            fields_schema = json.loads(note_type.fields_schema) if note_type.fields_schema else ["Front", "Back"]
            templates = json.loads(note_type.templates) if note_type.templates else []

            payload = BatchTaskPayload(
                doc_id=doc.id,
                doc_title=doc.title,
                doc_content=getattr(doc, "content", ""),
                deck_id=deck.id,
                model_id=note_type.id,
                note_type_fields=fields_schema,
                note_type_templates=templates,
                pipeline_id=pipeline_id,
                pipeline_steps=pipeline_steps,
                llm_id=llm_id,
                llm_config=llm_config,
                chunk_strategy=task["chunk_strategy"],
                use_vision=task["use_vision"],
            )
            tasks_payloads.append(payload)

        ai_provider = None
        if self.ai_manager and hasattr(self.ai_manager, "get_active_provider"):
            try:
                ai_provider = self.ai_manager.get_active_provider()
            except Exception:
                pass  # nosec B110

        self.btn_start.hide()
        self.btn_cancel.show()
        self.lbl_status_badge.setText("RUNNING")
        self.lbl_status_badge.setStyleSheet(f"color: {DesignTokens.COLOR_YELLOW};")

        self._log_terminal(f"\n> Launching AnkiForge Batch Factory for {len(tasks_payloads)} documents...")

        self.worker = BatchWorker(ai_provider=ai_provider, tasks=tasks_payloads)
        self.worker.batch_data_ready.connect(self._save_extracted_notes_to_db)
        self.worker.progress_val.connect(self.progress_bar.setValue)
        self.worker.progress_text.connect(lambda txt: self._log_terminal(f"> Progress: {txt}"))
        self.worker.log.connect(self._log_terminal)
        self.worker.finished.connect(self._on_batch_finished)
        self.worker.error.connect(self._on_batch_error)
        self.worker.cancelled.connect(self._on_batch_cancelled)

        self.worker.start()

    @Slot()
    def _on_cancel_batch(self) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.btn_cancel.setEnabled(False)
            self._log_terminal("> Stop request sent to Batch Engine...")

    @Slot(list, int, int)
    def _save_extracted_notes_to_db(self, notes_data: list[dict[str, Any]], deck_id: int, model_id: int) -> None:
        """Sauvegarde atomique et sécurisée des cartes générées (Logique master)."""
        try:
            deck = DeckModel.get_by_id(deck_id)
            note_type = NoteTypeModel.get_by_id(model_id)
            templates = json.loads(note_type.templates) if note_type.templates else []
            is_cloze = any("{{cloze:" in t.get("qfmt", "") or "{{cloze:" in t.get("afmt", "") for t in templates)

            with db.atomic():
                for cleaned_fields in notes_data:
                    note = NoteModel.create(
                        guid=str(uuid.uuid4())[:10],
                        note_type=note_type,
                        tags=json.dumps(["AnkiForge_Batch"], ensure_ascii=False),
                        status="pending",
                    )
                    NoteVersionModel.create(
                        note=note,
                        version_number=1,
                        content=json.dumps(cleaned_fields, ensure_ascii=False),
                        source="ai_batch",
                        is_active=True,
                    )

                    if is_cloze:
                        max_cloze = get_max_cloze_index(cleaned_fields)
                        num_cards = max(1, max_cloze)
                        for i in range(num_cards):
                            CardModel.create(note=note, deck=deck, template_index=i)
                    else:
                        for idx, _ in enumerate(templates):
                            CardModel.create(note=note, deck=deck, template_index=idx)

            self._log_terminal(f"> SUCCESS: {len(notes_data)} notes saved to deck '{deck.name}'")
        except Exception as e:
            logger.exception("Erreur lors de la sauvegarde batch dans la base : %s", e)
            self._log_terminal(f"> ERROR: Save failed - {str(e)}")

    @Slot(int, int)
    def _on_batch_finished(self, success_count: int, error_count: int) -> None:
        self._unlock_ui()
        self._log_terminal(f"\n> Batch completed: {success_count} success, {error_count} errors.")
        show_toast(self, f"Usine terminée : {success_count} documents traités avec succès !")
        self.queue_tasks_data.clear()
        self._update_queue_table()
        self._update_estimates()

    @Slot(str)
    def _on_batch_error(self, error_msg: str) -> None:
        self._unlock_ui()
        self._log_terminal(f"\n> CRITICAL ERROR: {error_msg}")
        QMessageBox.critical(self, "Erreur Usine", f"Le moteur Batch a rencontré une erreur :\n{error_msg}")

    @Slot()
    def _on_batch_cancelled(self) -> None:
        self._unlock_ui()
        self._log_terminal("\n> Batch engine stopped by user.")
        show_toast(self, "Usine arrêtée.", is_error=True)

    def _unlock_ui(self) -> None:
        self.btn_cancel.hide()
        self.btn_cancel.setEnabled(True)
        self.btn_start.show()
        self.lbl_status_badge.setText("READY")
        self.lbl_status_badge.setStyleSheet(f"color: {DesignTokens.COLOR_GREEN};")


BatchTab = BatchView

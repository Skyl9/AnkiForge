import json
import re
import uuid
from typing import Any

import qtawesome as qta
from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtGui import QShortcut, QKeySequence, QFont
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QComboBox, QSplitter, QTreeWidget,
                               QTreeWidgetItem, QAbstractItemView, QProgressBar,
                               QTextEdit, QMessageBox, QTableWidget, QTableWidgetItem, QHeaderView, QFrame, QGridLayout,
                               QSizePolicy)
from jinja2 import Template

from ankiforge.database.models import db, DeckModel, NoteTypeModel, NoteModel, CardModel, PipelineModel, \
    PipelineStepModel, \
    NoteVersionModel, DocumentModel, FolderModel, LLMConfigModel
from ankiforge.ui.components.components import ActionButton, PrimaryButton, DangerButton, RoundedPanel
from ankiforge.ui.widgets.toast import show_toast


class BatchWorker(QThread):
    """Thread de traitement par lots. Découpe les documents et exécute l'IA."""
    progress_val = Signal(int)
    progress_text = Signal(str)
    log = Signal(str)
    finished = Signal(int, int)  # (succès, erreurs)
    error = Signal(str)
    cancelled = Signal()

    def __init__(self, ai_provider: Any, tasks: list[dict[str, Any]]):
        super().__init__()
        self.ai_provider = ai_provider
        self.tasks = tasks
        self._is_cancelled = False

    def cancel(self) -> None:
        """Lève le drapeau d'annulation"""
        self._is_cancelled = True

    def _clean_json(self, raw_text: str) -> str:
        clean = raw_text.strip()
        if clean.startswith("```json"):
            clean = clean[7:-3].strip()
        elif clean.startswith("```"):
            clean = clean[3:-3].strip()
        return clean

    def _chunk_text(self, text: str, strategy: str, max_chars: int = 6000, overlap: int = 1000) -> list[str]:
        """Le moteur de découpage intelligent."""
        if strategy == "Aucun (Document entier)" or len(text) <= max_chars:
            return [text]

        chunks = []

        if strategy == "Sémantique (Titres)":
            # On cherche les titres Markdown (# Titre ou ## Titre)
            splits = [m.start() for m in re.finditer(r'(^|\n)(#{1,3})\s', text)]

            # Si le document n'a pas de titres, on bascule sur le Classique
            if not splits or len(splits) == 1:
                return self._chunk_text(text, "Classique", max_chars)

            last_idx = 0
            for i in range(1, len(splits)):
                part = text[last_idx:splits[i]].strip()
                if len(part) > 50:  # On ignore les morceaux vides
                    chunks.append(part)
                last_idx = splits[i]

            last_part = text[last_idx:].strip()
            if len(last_part) > 50:
                chunks.append(last_part)

            return chunks

        elif strategy == "Chevauchement (Overlap)":
            start = 0
            while start < len(text):
                end = start + max_chars
                if end >= len(text):
                    chunks.append(text[start:].strip())
                    break

                # On cherche une fin de phrase ou de paragraphe
                split_idx = text.rfind("\n\n", start, end)
                if split_idx == -1 or split_idx <= start + overlap:
                    split_idx = text.rfind(". ", start, end)
                if split_idx == -1 or split_idx <= start + overlap:
                    split_idx = end

                chunks.append(text[start:split_idx].strip())
                # On recule pour créer le chevauchement !
                start = split_idx - overlap
                if start < 0: start = 0

            return chunks

        else:  # "Classique"
            temp_text = text
            while len(temp_text) > 0:
                if len(temp_text) <= max_chars:
                    chunks.append(temp_text)
                    break

                split_idx = temp_text.rfind("\n\n", 0, max_chars)
                if split_idx == -1: split_idx = temp_text.rfind(". ", 0, max_chars)
                if split_idx == -1: split_idx = max_chars

                chunks.append(temp_text[:split_idx].strip())
                temp_text = temp_text[split_idx:].strip()

            return chunks

    def run(self) -> None:
        try:
            total_tasks = len(self.tasks)
            success_count = 0
            error_count = 0

            self.progress_val.emit(0)

            for task_idx, task in enumerate(self.tasks):
                if self._is_cancelled:
                    self.log.emit("Opération annulée par l'utilisateur")
                    self.cancelled.emit()
                    return


                doc = DocumentModel.get_by_id(task["doc_id"])
                deck = DeckModel.get_by_id(task["deck_id"])
                note_type = NoteTypeModel.get_by_id(task["model_id"])
                pipeline = PipelineModel.get_by_id(task["pipeline_id"])
                chunk_strategy = task["chunk_strategy"]

                steps = list(pipeline.steps.order_by(PipelineStepModel.step_order))

                llm_config = LLMConfigModel.get_by_id(task["llm_id"])
                max_tokens = llm_config.context_limit

                p_name = llm_config.provider.lower()
                if p_name == "ollama":
                    active_provider = OllamaProvider(model_name=llm_config.model_id)
                elif p_name == "gemini":
                    active_provider = GeminiService(model_name=llm_config.model_id)
                elif p_name == "groq":
                    active_provider = GroqProvider(model_name=llm_config.model_id)
                elif p_name == "openai":
                    active_provider = OpenAICompatibleProvider(
                        base_url="https://api.openai.com/v1",
                        model_name=llm_config.model_id,
                        api_key=os.environ.get("OPENAI_API_KEY", "")
                    )
                else:
                    active_provider = MockProvider()

                fields = json.loads(note_type.fields_schema) if note_type.fields_schema else ["Front", "Back"]
                fields_str = '", "'.join(fields)
                first_field = fields[0] if len(fields) > 0 else 'Field1'
                second_field = fields[1] if len(fields) > 1 else 'Field2'
                templates = json.loads(note_type.templates) if note_type.templates else []

                optimal_max_chars = int((max_tokens * 0.5) * 4)

                self.progress_text.emit(f"Traitement : {doc.title} ({task_idx + 1}/{total_tasks})...")
                self.log.emit(
                    f"\n{'=' * 40}\n📄 DEBUT : {doc.title}\n⚙️ Moteur : {llm_config.display_name} ({max_tokens} tks)\n{'=' * 40}")
                # PARTITIONNEMENT DU DOCUMENT
                chunks = self._chunk_text(doc.content, strategy=chunk_strategy, max_chars=optimal_max_chars)
                self.log.emit(f"✂️ Découpé en {len(chunks)} morceau(x) (Max chars: {optimal_max_chars}).")

                chunks = self._chunk_text(doc.content, strategy=chunk_strategy, max_chars=optimal_max_chars)
                doc_success_notes = 0

                for chunk_idx, chunk_text in enumerate(chunks, 1):
                    if self._is_cancelled:
                        self.log.emit("Opération annulée par l'utilisateur")
                        self.cancelled.emit()
                        return

                    self.log.emit(f"\n--- Morceau {chunk_idx}/{len(chunks)} ---")
                    current_input = f"TEXTE SOURCE :\n{chunk_text}"
                    cleaned_output = ""
                    chunk_failed = False

                    for step_idx, step in enumerate(steps, 1):
                        if self._is_cancelled:
                            self.log.emit("Opération annulée par l'utilisateur")
                            self.cancelled.emit()
                            return
                        agent = step.agent
                        self.log.emit(f"🤖 Agent '{agent.name}' en action...")

                        jinja_template = Template(agent.system_prompt)
                        system_prompt = jinja_template.render(
                            fields_str=fields_str, first_field=first_field, second_field=second_field
                        )

                        try:
                            raw_response = active_provider.generate(system_prompt=system_prompt,
                                                                     user_prompt=current_input)
                            cleaned_output = self._clean_json(raw_response)
                            current_input = f"Voici les données à traiter :\n{cleaned_output}"
                        except Exception as e:
                            self.log.emit(f"❌ ERREUR IA sur le morceau {chunk_idx}: {str(e)}")
                            chunk_failed = True
                            break

                    if chunk_failed:
                        continue

                    try:
                        data = json.loads(cleaned_output)
                        notes_to_create = data.get("notes", [])

                        if notes_to_create:
                            with db.atomic():
                                for note_data in notes_to_create:
                                    note = NoteModel.create(
                                        guid=str(uuid.uuid4())[:10], note_type=note_type,
                                        tags=json.dumps(["AnkiForge_Batch"]), status="pending"
                                    )
                                    NoteVersionModel.create(
                                        note=note, version_number=1, content=json.dumps(note_data, ensure_ascii=False),
                                        source="ai_batch", is_active=True
                                    )
                                    for idx, tmpl in enumerate(templates):
                                        CardModel.create(note=note, deck=deck, template_index=idx)

                            doc_success_notes += len(notes_to_create)
                            self.log.emit(f"✅ {len(notes_to_create)} cartes extraites.")
                    except json.JSONDecodeError:
                        self.log.emit(f"❌ ERREUR JSON : Format invalide.")

                if doc_success_notes > 0:
                    success_count += 1
                    self.log.emit(f"🎉 BILAN : {doc_success_notes} cartes générées au total pour '{doc.title}'.")
                else:
                    error_count += 1
                    self.log.emit(f"❌ ÉCHEC TOTAL : Aucune carte générée pour '{doc.title}'.")

                progress_pct = int(((task_idx + 1) / total_tasks) * 100)
                self.progress_val.emit(progress_pct)

            self.finished.emit(success_count, error_count)

        except Exception as e:
            self.error.emit(f"Erreur fatale du BatchWorker : {str(e)}")


class BatchTab(QWidget):
    def __init__(self, ai_manager: Any) -> None:
        super().__init__()
        self.ai_manager = ai_manager
        self.chunk_strategies = ["Sémantique (Titres)", "Chevauchement (Overlap)", "Classique",
                                 "Aucun (Document entier)"]

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)

        titles_layout = QVBoxLayout()
        titles_layout.setSpacing(2)

        header = QLabel("⚙️ Automatisation Avancée (Usine à cartes)")
        header.setStyleSheet("font-size: 15px; font-weight: bold; color: palette(text);")
        header.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)

        subtitle = QLabel("Gérez votre file d'attente et personnalisez le traitement pour chaque document.")
        subtitle.setStyleSheet("color: palette(placeholder-text); font-size: 11px;")
        subtitle.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)

        titles_layout.addWidget(header)
        titles_layout.addWidget(subtitle)

        layout.addLayout(titles_layout)

        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_splitter.setHandleWidth(10)
        main_splitter.setChildrenCollapsible(False)

        # ==========================================
        # PANNEAU GAUCHE : Source des documents
        # ==========================================
        source_panel = RoundedPanel()
        source_layout = QVBoxLayout(source_panel)
        source_layout.setContentsMargins(15, 15, 15, 15)

        lbl_source = QLabel("1. SOURCE (COURS ET DOSSIERS)")
        lbl_source.setStyleSheet(
            "font-weight: bold; color: palette(placeholder-text); font-size: 11px; letter-spacing: 1px; margin-bottom: 5px;")
        source_layout.addWidget(lbl_source)

        self.tree_source = QTreeWidget()
        self.tree_source.setHeaderHidden(True)
        self.tree_source.setFrameShape(QFrame.Shape.NoFrame)
        self.tree_source.viewport().setAutoFillBackground(False)
        self.tree_source.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        source_layout.addWidget(self.tree_source)

        self.btn_add_to_queue = ActionButton('fa5s.arrow-right', " Ajouter à la file d'attente")
        self.btn_add_to_queue.clicked.connect(self.add_selected_to_queue)
        source_layout.addWidget(self.btn_add_to_queue)

        main_splitter.addWidget(source_panel)

        # ==========================================
        # PANNEAU DROIT : File d'attente et Console
        # ==========================================
        right_splitter = QSplitter(Qt.Orientation.Vertical)
        right_splitter.setHandleWidth(10)

        # --- 2A. File d'attente et Configuration ---
        queue_panel = RoundedPanel()
        queue_layout = QVBoxLayout(queue_panel)
        queue_layout.setContentsMargins(15, 15, 15, 15)

        lbl_config = QLabel("CONFIGURATION PAR DÉFAUT")
        lbl_config.setStyleSheet(
            "font-weight: bold; color: palette(placeholder-text); font-size: 11px; letter-spacing: 1px; margin-bottom: 5px;")
        queue_layout.addWidget(lbl_config)

        default_params_layout = QGridLayout()

        self.default_deck = QComboBox()
        self.default_deck.setMinimumWidth(80)
        self.default_model = QComboBox()
        self.default_model.setMinimumWidth(80)
        self.default_llm = QComboBox()
        self.default_llm.setMinimumWidth(80)
        self.default_pipeline = QComboBox()
        self.default_pipeline.setMinimumWidth(80)
        self.default_chunking = QComboBox()
        self.default_chunking.setMinimumWidth(80)
        self.default_chunking.addItems(self.chunk_strategies)

        # Ajout des labels en ligne 0
        default_params_layout.addWidget(QLabel("Paquet :"), 0, 0)
        default_params_layout.addWidget(QLabel("Modèle :"), 0, 1)
        default_params_layout.addWidget(QLabel("Moteur :"), 0, 2)
        default_params_layout.addWidget(QLabel("Pipeline :"), 0, 3)
        default_params_layout.addWidget(QLabel("Découpage :"), 0, 4)

        # Ajout des champs en ligne 1
        default_params_layout.addWidget(self.default_deck, 1, 0)
        default_params_layout.addWidget(self.default_model, 1, 1)
        default_params_layout.addWidget(self.default_llm, 1, 2)
        default_params_layout.addWidget(self.default_pipeline, 1, 3)
        default_params_layout.addWidget(self.default_chunking, 1, 4)

        lbl_queue = QLabel("2. FILE D'ATTENTE")
        lbl_queue.setStyleSheet(
            "font-weight: bold; color: palette(placeholder-text); font-size: 11px; letter-spacing: 1px; margin-top: 15px; margin-bottom: 5px;")
        queue_layout.addWidget(lbl_queue)

        self.table_queue = QTableWidget()
        self.table_queue.setFrameShape(QFrame.Shape.NoFrame)
        self.table_queue.setColumnCount(7)
        # 🐛 CORRECTION DU BUG : Virgule manquante entre Moteur IA et Pipeline IA !
        self.table_queue.setHorizontalHeaderLabels(
            ["Document", "Paquet", "Modèle", "Moteur IA", "Pipeline IA", "Découpage", "Action"])
        self.table_queue.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table_queue.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table_queue.setAlternatingRowColors(True)

        self.lbl_empty_queue = QLabel("La file d'attente est vide. Sélectionnez des documents à gauche pour commencer.")
        self.lbl_empty_queue.setStyleSheet("color: palette(placeholder-text); font-style: italic;")
        self.lbl_empty_queue.setAlignment(Qt.AlignmentFlag.AlignCenter)
        queue_layout.addWidget(self.lbl_empty_queue)

        queue_layout.addWidget(self.table_queue)

        right_splitter.addWidget(queue_panel)

        # --- 2B. Console de suivi ---
        console_panel = RoundedPanel()
        console_layout = QVBoxLayout(console_panel)
        console_layout.setContentsMargins(15, 15, 15, 15)

        lbl_console = QLabel("CONSOLE DE SUIVI")
        lbl_console.setStyleSheet(
            "font-weight: bold; color: palette(placeholder-text); font-size: 11px; letter-spacing: 1px; margin-bottom: 5px;")
        console_layout.addWidget(lbl_console)

        self.console_log = QTextEdit()
        self.console_log.setReadOnly(True)
        self.console_log.setFrameShape(QFrame.Shape.NoFrame)
        self.console_log.viewport().setAutoFillBackground(False)
        font = QFont("Consolas")
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.console_log.setFont(font)
        console_layout.addWidget(self.console_log)

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

        self.lbl_status = QLabel("Prêt.")
        self.lbl_status.setStyleSheet(
            "color: palette(placeholder-text); font-size: 12px; margin-left: 10px; margin-right: 10px;")
        bottom_layout.addWidget(self.lbl_status)

        self.btn_start = PrimaryButton(qta.icon('fa5s.rocket', color='white'), " Démarrer l'Usine")
        self.btn_start.clicked.connect(self.start_batch)
        self.btn_start.setMinimumWidth(200)
        bottom_layout.addWidget(self.btn_start)

        self.btn_cancel = DangerButton(qta.icon('fa5s.stop', color='white'), " Annuler le traitement")
        self.btn_cancel.clicked.connect(self.cancel_batch)
        self.btn_cancel.setMinimumWidth(200)
        self.btn_cancel.hide()
        bottom_layout.addWidget(self.btn_cancel)

        console_layout.addLayout(bottom_layout)
        right_splitter.addWidget(console_panel)

        right_splitter.setSizes([350, 300])

        source_panel.setMinimumWidth(150)
        right_splitter.setMinimumWidth(300)

        main_splitter.addWidget(source_panel)
        main_splitter.addWidget(right_splitter)
        main_splitter.setSizes([250, 950])

        layout.addWidget(main_splitter)

        self.refresh_selectors()
        self.load_tree_source()

        # --- RACCOURCIS CLAVIER ---
        self.shortcut_start = QShortcut(QKeySequence("Ctrl+Return"), self)
        self.shortcut_start.activated.connect(self.start_batch)
        self.shortcut_remove_queue = QShortcut(QKeySequence.StandardKey.Delete, self.table_queue)
        self.shortcut_remove_queue.activated.connect(self._remove_selected_from_table)

    @Slot()
    def refresh_data(self) -> None:
        """Contrat MainWindow : Rafraîchit les listes et les dossiers."""
        self.refresh_selectors()
        self.load_tree_source()

    @Slot()
    def load_tree_source(self) -> None:
        self.tree_source.clear()
        folders = FolderModel.select().order_by(FolderModel.name)
        for folder in folders:
            folder_item = QTreeWidgetItem(self.tree_source, [f" {folder.name}"])
            folder_item.setIcon(0, qta.icon('fa5s.folder', color='#FFC107'))
            folder_item.setData(0, Qt.ItemDataRole.UserRole, {"type": "folder", "id": folder.id})

            docs = DocumentModel.select().where(DocumentModel.folder == folder).order_by(DocumentModel.title)
            for doc in docs:
                doc_item = QTreeWidgetItem(folder_item, [f" {doc.title}"])
                doc_item.setIcon(0, qta.icon('fa5s.file-alt', color='#90CAF9'))
                doc_item.setData(0, Qt.ItemDataRole.UserRole, {"type": "doc", "id": doc.id, "title": doc.title})

        orphan_docs = DocumentModel.select().where(DocumentModel.folder.is_null()).order_by(DocumentModel.title)
        orphan_root = QTreeWidgetItem(self.tree_source, [" Non classés"])
        orphan_root.setIcon(0, qta.icon('fa5s.box-open', color='#B0BEC5'))
        for doc in orphan_docs:
            doc_item = QTreeWidgetItem(orphan_root, [f" {doc.title}"])
            doc_item.setIcon(0, qta.icon('fa5s.file-alt', color='#90CAF9'))
            doc_item.setData(0, Qt.ItemDataRole.UserRole, {"type": "doc", "id": doc.id, "title": doc.title})

        self.tree_source.expandAll()

    @Slot()
    def refresh_selectors(self) -> None:
        self.default_deck.clear()
        for deck in DeckModel.select().order_by(DeckModel.name):
            self.default_deck.addItem(deck.name, userData=deck.id)

        self.default_model.clear()
        for nt in NoteTypeModel.select().order_by(NoteTypeModel.name):
            self.default_model.addItem(nt.name, userData=nt.id)

        self.default_pipeline.clear()
        for pipe in PipelineModel.select().order_by(PipelineModel.name):
            self.default_pipeline.addItem(pipe.name, userData=pipe.id)

        self.default_llm.clear()
        for llm in LLMConfigModel.select().order_by(LLMConfigModel.display_name):
            self.default_llm.addItem(llm.display_name, userData=llm.id)

    @Slot()
    def add_selected_to_queue(self) -> None:
        selected_items = self.tree_source.selectedItems()
        if not selected_items: return

        docs_to_add = []
        for item in selected_items:
            data = item.data(0, Qt.UserRole)
            if not data: continue

            if data.get("type") == "doc":
                docs_to_add.append(data)
            elif data.get("type") == "folder" and data.get("id") is not None:
                folder_docs = DocumentModel.select().where(DocumentModel.folder_id == data["id"])
                for d in folder_docs: docs_to_add.append({"id": d.id, "title": d.title})

        for doc_data in docs_to_add:
            self._add_row_to_queue(doc_data["id"], doc_data["title"])

        self._check_ready_state()

    def _add_row_to_queue(self, doc_id: int, title: str) -> None:
        row_idx = self.table_queue.rowCount()
        self.table_queue.insertRow(row_idx)

        # 1. Document
        item_doc = QTableWidgetItem(f"📄 {title}")
        item_doc.setData(Qt.UserRole, doc_id)
        self.table_queue.setItem(row_idx, 0, item_doc)

        # 2. Paquet
        cb_deck = QComboBox()
        for i in range(self.default_deck.count()): cb_deck.addItem(self.default_deck.itemText(i),
                                                                   self.default_deck.itemData(i))
        cb_deck.setCurrentIndex(self.default_deck.currentIndex())
        self.table_queue.setCellWidget(row_idx, 1, cb_deck)

        # 3. Modèle de carte
        cb_model = QComboBox()
        for i in range(self.default_model.count()): cb_model.addItem(self.default_model.itemText(i),
                                                                     self.default_model.itemData(i))
        cb_model.setCurrentIndex(self.default_model.currentIndex())
        self.table_queue.setCellWidget(row_idx, 2, cb_model)

        # 4. Moteur IA (NOUVEAU)
        cb_llm = QComboBox()
        for i in range(self.default_llm.count()):
            cb_llm.addItem(self.default_llm.itemText(i), self.default_llm.itemData(i))
        cb_llm.setCurrentIndex(self.default_llm.currentIndex())
        self.table_queue.setCellWidget(row_idx, 3, cb_llm)

        # 5. Pipeline
        cb_pipe = QComboBox()
        for i in range(self.default_pipeline.count()): cb_pipe.addItem(self.default_pipeline.itemText(i),
                                                                       self.default_pipeline.itemData(i))
        cb_pipe.setCurrentIndex(self.default_pipeline.currentIndex())
        self.table_queue.setCellWidget(row_idx, 4, cb_pipe)

        # 6. Découpage
        cb_chunk = QComboBox()
        cb_chunk.addItems(self.chunk_strategies)
        cb_chunk.setCurrentIndex(self.default_chunking.currentIndex())
        self.table_queue.setCellWidget(row_idx, 5, cb_chunk)

        # 7. Action

        btn_remove = DangerButton(qta.icon('fa5s.times', color='white'), "")
        btn_remove.clicked.connect(lambda _, r=row_idx: self._remove_row(r))
        self.table_queue.setCellWidget(row_idx, 6, btn_remove)

    def _remove_row(self, row_idx: int) -> None:
        self.table_queue.removeRow(row_idx)
        for r in range(row_idx, self.table_queue.rowCount()):
            btn = self.table_queue.cellWidget(r, 6)
            btn.clicked.disconnect()
            btn.clicked.connect(lambda _, current_r=r: self._remove_row(current_r))
        self._check_ready_state()

    def _check_ready_state(self) -> None:
        count = self.table_queue.rowCount()
        self.btn_start.setEnabled(count > 0)
        self.lbl_status.setText(f"{count} document(s) dans la file d'attente.")
        self.lbl_empty_queue.setVisible(count == 0)  # 👈 Ajout
        self.table_queue.setVisible(count > 0)

    @Slot(str)
    def append_log(self, text: str) -> None:
        self.console_log.append(text)
        scrollbar = self.console_log.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    @Slot()
    def start_batch(self) -> None:
        if self.table_queue.rowCount() == 0: return

        tasks = []
        for row in range(self.table_queue.rowCount()):
            doc_id = self.table_queue.item(row, 0).data(Qt.UserRole)
            deck_id = self.table_queue.cellWidget(row, 1).currentData()
            model_id = self.table_queue.cellWidget(row, 2).currentData()

            # 🐛 CORRECTION DES BUGS D'INDEX ICI 👇
            llm_id = self.table_queue.cellWidget(row, 3).currentData()
            pipe_id = self.table_queue.cellWidget(row, 4).currentData()
            chunk_strategy = self.table_queue.cellWidget(row, 5).currentText()

            if not deck_id or not model_id or not pipe_id:
                show_toast(self, f"Configuration incomplète à la ligne {row + 1}.", is_error=True)
                return

            tasks.append({
                "doc_id": doc_id, "deck_id": deck_id,
                "model_id": model_id, "llm_id": llm_id,
                "pipeline_id": pipe_id, "chunk_strategy": chunk_strategy
            })

        self.btn_start.hide()
        self.btn_cancel.show()
        self.btn_cancel.setEnabled(True)

        self.btn_add_to_queue.setEnabled(False)
        self.table_queue.setEnabled(False)
        self.console_log.clear()
        self.progress_bar.setValue(0)

        self.append_log(f"🚀 Lancement de l'Usine : {len(tasks)} document(s) à traiter.")

        self.worker = BatchWorker(ai_provider=self.ai_manager.provider, tasks=tasks)
        self.worker.progress_val.connect(self.progress_bar.setValue)
        self.worker.progress_text.connect(self.lbl_status.setText)
        self.worker.log.connect(self.append_log)
        self.worker.finished.connect(self.on_batch_finished)
        self.worker.error.connect(self.on_batch_error)
        self.worker.cancelled.connect(self.on_batch_cancelled)

        self.worker.start()

    @Slot()
    def cancel_batch(self) -> None:
        """Demande l'arrêt propre du worker."""
        if hasattr(self, 'worker') and self.worker.isRunning():
            self.worker.cancel()
            self.btn_cancel.setEnabled(False)
            self.btn_cancel.setText(" Arrêt en cours...")
            self.lbl_status.setText("Annulation demandée, attente de l'arrêt...")
            self.append_log("⏳ Demande d'arrêt envoyée. Attente de la fin du cycle en cours...")

    @Slot(int, int)
    def on_batch_finished(self, success_count: int, error_count: int) -> None:
        self._unlock_ui()
        self.lbl_status.setText("Terminé.")
        msg = f"Traitement de la file d'attente terminé.\n\n✅ Documents réussis : {success_count}\n❌ Documents échoués : {error_count}"
        self.append_log(f"\n{'=' * 40}\n{msg}")
        (show_toast(self, "Traitement par lots terminé !"))

    @Slot(str)
    def on_batch_error(self, error_msg: str) -> None:
        self._unlock_ui()
        self.lbl_status.setText("Erreur fatale.")
        QMessageBox.critical(self, "Erreur Fatale", error_msg)

    @Slot()
    def on_batch_cancelled(self) -> None:
        """Gère l'interface une fois le worker effectivement arrêté."""
        self._unlock_ui()
        self.lbl_status.setText("Traitement annulé.")
        show_toast(self, "L'opération a été annulée proprement.", is_error=True)

    def _unlock_ui(self) -> None:
        """Restaure l'interface."""
        self.btn_cancel.hide()
        self.btn_cancel.setText(" Annuler le traitement")
        self.btn_start.show()
        self.btn_start.setEnabled(True)
        self.btn_add_to_queue.setEnabled(True)
        self.table_queue.setEnabled(True)

    @Slot()
    def _remove_selected_from_table(self) -> None:
        """Supprime la ligne actuellement sélectionnée dans la table de file d'attente."""
        current_row = self.table_queue.currentRow()
        if current_row != -1:
            self._remove_row(current_row)

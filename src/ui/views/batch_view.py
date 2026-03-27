# src/ui/views/batch_view.py
import json
import uuid
from typing import Any, List, Dict

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton, QComboBox, QSplitter, QTreeWidget,
                               QTreeWidgetItem, QAbstractItemView, QProgressBar,
                               QTextEdit, QMessageBox, QTableWidget, QTableWidgetItem, QHeaderView)
from jinja2 import Template

from src.database.models import db, DeckModel, NoteTypeModel, NoteModel, CardModel, PipelineModel, PipelineStepModel, \
    NoteVersionModel, DocumentModel, FolderModel


class BatchWorker(QThread):
    """Thread de traitement par lots. Découpe les documents et exécute l'IA."""
    progress_val = Signal(int)
    progress_text = Signal(str)
    log = Signal(str)
    finished = Signal(int, int)  # (succès, erreurs)
    error = Signal(str)

    def __init__(self, ai_provider: Any, tasks: List[Dict[str, int]]):
        super().__init__()
        self.ai_provider = ai_provider
        self.tasks = tasks  # Liste de dicts: [{"doc_id": 1, "deck_id": 2, "model_id": 1, "pipeline_id": 1}, ...]

    def _clean_json(self, raw_text: str) -> str:
        clean = raw_text.strip()
        if clean.startswith("```json"):
            clean = clean[7:-3].strip()
        elif clean.startswith("```"):
            clean = clean[3:-3].strip()
        return clean

    def _chunk_text(self, text: str, max_chars: int = 6000) -> List[str]:
        """Découpe un long texte en morceaux pour éviter l'overflow de l'IA (Chunking)."""
        if len(text) <= max_chars:
            return [text]

        chunks = []
        while len(text) > 0:
            if len(text) <= max_chars:
                chunks.append(text)
                break

            # On cherche le dernier double retour à la ligne avant la limite pour ne pas couper un paragraphe
            split_idx = text.rfind("\n\n", 0, max_chars)
            # Si pas de double retour, on cherche un point
            if split_idx == -1:
                split_idx = text.rfind(". ", 0, max_chars)
            # Sinon on coupe brutalement
            if split_idx == -1:
                split_idx = max_chars

            chunks.append(text[:split_idx].strip())
            text = text[split_idx:].strip()

        return chunks

    def run(self) -> None:
        try:
            total_tasks = len(self.tasks)
            success_count = 0
            error_count = 0

            self.progress_val.emit(0)

            # Boucle Principale sur les tâches (documents)
            for task_idx, task in enumerate(self.tasks):
                doc = DocumentModel.get_by_id(task["doc_id"])
                deck = DeckModel.get_by_id(task["deck_id"])
                note_type = NoteTypeModel.get_by_id(task["model_id"])
                pipeline = PipelineModel.get_by_id(task["pipeline_id"])
                steps = list(pipeline.steps.order_by(PipelineStepModel.step_order))

                fields = json.loads(note_type.fields_schema) if note_type.fields_schema else ["Front", "Back"]
                fields_str = '", "'.join(fields)
                first_field = fields[0] if len(fields) > 0 else 'Field1'
                second_field = fields[1] if len(fields) > 1 else 'Field2'
                templates = json.loads(note_type.templates) if note_type.templates else []

                self.progress_text.emit(f"Traitement : {doc.title} ({task_idx + 1}/{total_tasks})...")
                self.log.emit(f"\n{'=' * 40}\n📄 DEBUT : {doc.title}\n{'=' * 40}")

                # PARTITIONNEMENT DU DOCUMENT
                chunks = self._chunk_text(doc.content, max_chars=6000)
                self.log.emit(f"✂️ Document découpé en {len(chunks)} morceau(x) pour l'IA.")

                doc_success_notes = 0

                for chunk_idx, chunk_text in enumerate(chunks, 1):
                    self.log.emit(f"\n--- Traitement du morceau {chunk_idx}/{len(chunks)} ---")
                    current_input = f"TEXTE SOURCE :\n{chunk_text}"
                    cleaned_output = ""
                    chunk_failed = False

                    # Exécution du Pipeline IA sur ce morceau
                    for step_idx, step in enumerate(steps, 1):
                        agent = step.agent
                        self.log.emit(f"🤖 Agent '{agent.name}' en action...")

                        jinja_template = Template(agent.system_prompt)
                        system_prompt = jinja_template.render(
                            fields_str=fields_str, first_field=first_field, second_field=second_field
                        )

                        try:
                            raw_response = self.ai_provider.generate(system_prompt=system_prompt,
                                                                     user_prompt=current_input)
                            cleaned_output = self._clean_json(raw_response)
                            current_input = f"Voici les données à traiter :\n{cleaned_output}"
                        except Exception as e:
                            self.log.emit(f"❌ ERREUR IA sur le morceau {chunk_idx}: {str(e)}")
                            chunk_failed = True
                            break

                    if chunk_failed:
                        continue  # On passe au morceau suivant si celui-ci a planté

                    # Sauvegarde Directe du morceau en BDD
                    try:
                        data = json.loads(cleaned_output)
                        notes_to_create = data.get("notes", [])

                        if notes_to_create:
                            with db.atomic():
                                for note_data in notes_to_create:
                                    note = NoteModel.create(
                                        guid=str(uuid.uuid4())[:10], note_type=note_type,
                                        tags=json.dumps(["AnkiForge_Batch"]), status="new"
                                    )
                                    NoteVersionModel.create(
                                        note=note, version_number=1, content=json.dumps(note_data, ensure_ascii=False),
                                        source="ai_batch", is_active=True
                                    )
                                    for idx, tmpl in enumerate(templates):
                                        CardModel.create(note=note, deck=deck, template_index=idx)

                            doc_success_notes += len(notes_to_create)
                            self.log.emit(f"✅ {len(notes_to_create)} cartes extraites du morceau {chunk_idx}.")
                    except json.JSONDecodeError:
                        self.log.emit(f"❌ ERREUR JSON : Format invalide sur le morceau {chunk_idx}.")

                # Bilan du document
                if doc_success_notes > 0:
                    success_count += 1
                    self.log.emit(f"🎉 BILAN : {doc_success_notes} cartes générées au total pour '{doc.title}'.")
                else:
                    error_count += 1
                    self.log.emit(f"❌ ÉCHEC TOTAL : Aucune carte générée pour '{doc.title}'.")

                # Mise à jour de la barre
                progress_pct = int(((task_idx + 1) / total_tasks) * 100)
                self.progress_val.emit(progress_pct)

            self.finished.emit(success_count, error_count)

        except Exception as e:
            self.error.emit(f"Erreur fatale du BatchWorker : {str(e)}")


class BatchTab(QWidget):
    """Interface utilisateur pour le traitement par lots avec File d'attente (Queue)."""

    def __init__(self, ai_manager: Any) -> None:
        super().__init__()
        self.ai_manager = ai_manager

        layout = QVBoxLayout(self)

        # 1. En-tête
        header = QLabel(
            "<b>⚙️ Automatisation Avancée (Usine à cartes)</b><br>Gérez votre file d'attente et personnalisez le traitement pour chaque document.")
        header.setStyleSheet("font-size: 16px; margin-bottom: 10px;")
        layout.addWidget(header)

        main_splitter = QSplitter(Qt.Horizontal)

        # --- PANNEAU GAUCHE : SÉLECTION (Arbre) ---
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        left_layout.addWidget(QLabel("<b>📄 1. Source (Cours et Dossiers) :</b>"))

        self.tree_source = QTreeWidget()
        self.tree_source.setHeaderHidden(True)
        self.tree_source.setSelectionMode(QAbstractItemView.ExtendedSelection)
        left_layout.addWidget(self.tree_source)

        self.btn_add_to_queue = QPushButton("➡️ Ajouter à la file d'attente")
        self.btn_add_to_queue.setStyleSheet("background-color: #2196F3; color: white; font-weight: bold; padding: 8px;")
        self.btn_add_to_queue.clicked.connect(self.add_selected_to_queue)
        left_layout.addWidget(self.btn_add_to_queue)

        # --- PANNEAU DROIT : FILE D'ATTENTE & CONSOLE ---
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # Paramètres par défaut (pour remplir rapidement le tableau)
        default_params_layout = QHBoxLayout()
        default_params_layout.addWidget(QLabel("<b>⚙️ Configuration par défaut :</b>"))

        self.default_deck = QComboBox()
        self.default_model = QComboBox()
        self.default_pipeline = QComboBox()

        default_params_layout.addWidget(self.default_deck)
        default_params_layout.addWidget(self.default_model)
        default_params_layout.addWidget(self.default_pipeline)
        right_layout.addLayout(default_params_layout)

        right_layout.addWidget(QLabel("<b>📋 2. File d'attente :</b>"))

        # LE TABLEAU DE LA FILE D'ATTENTE
        self.table_queue = QTableWidget()
        self.table_queue.setColumnCount(5)
        self.table_queue.setHorizontalHeaderLabels(["Document", "Paquet Cible", "Modèle Anki", "Pipeline IA", "Action"])
        self.table_queue.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table_queue.setEditTriggers(QAbstractItemView.NoEditTriggers)
        right_layout.addWidget(self.table_queue)

        # Console de logs
        right_layout.addWidget(QLabel("<b>🕵️ Console de Suivi :</b>"))
        self.console_log = QTextEdit()
        self.console_log.setReadOnly(True)
        self.console_log.setStyleSheet(
            "background-color: #1e1e1e; color: #d4d4d4; font-family: 'Consolas', monospace; padding: 5px;")
        right_layout.addWidget(self.console_log)

        # Barre de progression et Bouton
        bottom_layout = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        bottom_layout.addWidget(self.progress_bar)

        self.lbl_status = QLabel("Prêt.")
        bottom_layout.addWidget(self.lbl_status)

        self.btn_start = QPushButton("🚀 Démarrer l'Usine")
        self.btn_start.setStyleSheet("background-color: #673AB7; color: white; font-weight: bold; padding: 12px;")
        self.btn_start.clicked.connect(self.start_batch)
        bottom_layout.addWidget(self.btn_start)

        right_layout.addLayout(bottom_layout)

        # Ajout au splitter
        main_splitter.addWidget(left_panel)
        main_splitter.addWidget(right_panel)
        main_splitter.setSizes([250, 850])

        layout.addWidget(main_splitter)

        self.refresh_selectors()
        self.load_tree_source()

    # ==========================================
    # LOGIQUE INTERFACE
    # ==========================================

    def load_tree_source(self) -> None:
        """Charge l'arbre des documents comme dans le gestionnaire de fichiers."""
        self.tree_source.clear()

        folders = FolderModel.select().order_by(FolderModel.name)
        for folder in folders:
            folder_item = QTreeWidgetItem(self.tree_source, [f"📂 {folder.name}"])
            folder_item.setData(0, Qt.UserRole, {"type": "folder", "id": folder.id})

            docs = DocumentModel.select().where(DocumentModel.folder == folder).order_by(DocumentModel.title)
            for doc in docs:
                doc_item = QTreeWidgetItem(folder_item, [f"📄 {doc.title}"])
                doc_item.setData(0, Qt.UserRole, {"type": "doc", "id": doc.id, "title": doc.title})

        orphan_docs = DocumentModel.select().where(DocumentModel.folder.is_null()).order_by(DocumentModel.title)
        orphan_root = QTreeWidgetItem(self.tree_source, ["📂 Non classés"])
        for doc in orphan_docs:
            doc_item = QTreeWidgetItem(orphan_root, [f"📄 {doc.title}"])
            doc_item.setData(0, Qt.UserRole, {"type": "doc", "id": doc.id, "title": doc.title})

        self.tree_source.expandAll()

    def refresh_selectors(self) -> None:
        """Charge les données dans les ComboBox par défaut."""
        self.default_deck.clear()
        for deck in DeckModel.select().order_by(DeckModel.name):
            self.default_deck.addItem(deck.name, userData=deck.id)

        self.default_model.clear()
        for nt in NoteTypeModel.select().order_by(NoteTypeModel.name):
            self.default_model.addItem(nt.name, userData=nt.id)

        self.default_pipeline.clear()
        for pipe in PipelineModel.select().order_by(PipelineModel.name):
            self.default_pipeline.addItem(pipe.name, userData=pipe.id)

    def add_selected_to_queue(self) -> None:
        """Ajoute les documents sélectionnés (ou le contenu des dossiers) à la table."""
        selected_items = self.tree_source.selectedItems()
        if not selected_items:
            return

        docs_to_add = []
        for item in selected_items:
            data = item.data(0, Qt.UserRole)
            if not data: continue

            if data.get("type") == "doc":
                docs_to_add.append(data)
            elif data.get("type") == "folder" and data.get("id") is not None:
                # On ajoute tous les documents de ce dossier
                folder_docs = DocumentModel.select().where(DocumentModel.folder_id == data["id"])
                for d in folder_docs:
                    docs_to_add.append({"id": d.id, "title": d.title})

        for doc_data in docs_to_add:
            self._add_row_to_queue(doc_data["id"], doc_data["title"])

        self._check_ready_state()

    def _add_row_to_queue(self, doc_id: int, title: str) -> None:
        """Ajoute une ligne dans le QTableWidget avec ses propres ComboBox."""
        row_idx = self.table_queue.rowCount()
        self.table_queue.insertRow(row_idx)

        # 1. Colonne Document
        item_doc = QTableWidgetItem(f"📄 {title}")
        item_doc.setData(Qt.UserRole, doc_id)
        self.table_queue.setItem(row_idx, 0, item_doc)

        # 2. Colonne Paquet
        cb_deck = QComboBox()
        for i in range(self.default_deck.count()):
            cb_deck.addItem(self.default_deck.itemText(i), self.default_deck.itemData(i))
        cb_deck.setCurrentIndex(self.default_deck.currentIndex())  # Hérite du défaut
        self.table_queue.setCellWidget(row_idx, 1, cb_deck)

        # 3. Colonne Modèle
        cb_model = QComboBox()
        for i in range(self.default_model.count()):
            cb_model.addItem(self.default_model.itemText(i), self.default_model.itemData(i))
        cb_model.setCurrentIndex(self.default_model.currentIndex())
        self.table_queue.setCellWidget(row_idx, 2, cb_model)

        # 4. Colonne Pipeline
        cb_pipe = QComboBox()
        for i in range(self.default_pipeline.count()):
            cb_pipe.addItem(self.default_pipeline.itemText(i), self.default_pipeline.itemData(i))
        cb_pipe.setCurrentIndex(self.default_pipeline.currentIndex())
        self.table_queue.setCellWidget(row_idx, 3, cb_pipe)

        # 5. Colonne Action (Supprimer)
        btn_remove = QPushButton("❌")
        btn_remove.setStyleSheet("color: red; font-weight: bold;")
        btn_remove.clicked.connect(lambda _, r=row_idx: self._remove_row(r))
        self.table_queue.setCellWidget(row_idx, 4, btn_remove)

    def _remove_row(self, row_idx: int) -> None:
        """Supprime une ligne et met à jour les connexions des boutons suivants."""
        self.table_queue.removeRow(row_idx)
        # Il faut recâbler les boutons ❌ en dessous pour qu'ils suppriment la bonne ligne
        for r in range(row_idx, self.table_queue.rowCount()):
            btn = self.table_queue.cellWidget(r, 4)
            btn.clicked.disconnect()
            btn.clicked.connect(lambda _, current_r=r: self._remove_row(current_r))
        self._check_ready_state()

    def _check_ready_state(self) -> None:
        count = self.table_queue.rowCount()
        self.btn_start.setEnabled(count > 0)
        self.lbl_status.setText(f"{count} document(s) dans la file d'attente.")

    def append_log(self, text: str) -> None:
        self.console_log.append(text)
        scrollbar = self.console_log.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    # ==========================================
    # LOGIQUE D'EXÉCUTION
    # ==========================================

    def start_batch(self) -> None:
        if self.table_queue.rowCount() == 0:
            return

        # 1. On lit le tableau pour construire la liste des tâches
        tasks = []
        for row in range(self.table_queue.rowCount()):
            doc_id = self.table_queue.item(row, 0).data(Qt.UserRole)
            deck_id = self.table_queue.cellWidget(row, 1).currentData()
            model_id = self.table_queue.cellWidget(row, 2).currentData()
            pipe_id = self.table_queue.cellWidget(row, 3).currentData()

            if not deck_id or not model_id or not pipe_id:
                QMessageBox.warning(self, "Erreur", f"Configuration incomplète à la ligne {row + 1}.")
                return

            tasks.append({
                "doc_id": doc_id, "deck_id": deck_id,
                "model_id": model_id, "pipeline_id": pipe_id
            })

        # 2. Verrouillage de l'UI
        self.btn_start.setEnabled(False)
        self.btn_add_to_queue.setEnabled(False)
        self.table_queue.setEnabled(False)
        self.console_log.clear()
        self.progress_bar.setValue(0)

        self.append_log(f"🚀 Lancement de l'Usine : {len(tasks)} document(s) à traiter.")

        # 3. Lancement du Thread
        self.worker = BatchWorker(ai_provider=self.ai_manager.provider, tasks=tasks)
        self.worker.progress_val.connect(self.progress_bar.setValue)
        self.worker.progress_text.connect(self.lbl_status.setText)
        self.worker.log.connect(self.append_log)
        self.worker.finished.connect(self.on_batch_finished)
        self.worker.error.connect(self.on_batch_error)

        self.worker.start()

    def on_batch_finished(self, success_count: int, error_count: int) -> None:
        self._unlock_ui()
        self.lbl_status.setText("Terminé.")

        msg = f"Traitement de la file d'attente terminé.\n\n✅ Documents réussis : {success_count}\n❌ Documents échoués : {error_count}"
        self.append_log(f"\n{'=' * 40}\n{msg}")
        QMessageBox.information(self, "Bilan de l'Usine", msg)

    def on_batch_error(self, error_msg: str) -> None:
        self._unlock_ui()
        self.lbl_status.setText("Erreur fatale.")
        QMessageBox.critical(self, "Erreur Fatale", error_msg)

    def _unlock_ui(self) -> None:
        self.btn_start.setEnabled(True)
        self.btn_add_to_queue.setEnabled(True)
        self.table_queue.setEnabled(True)

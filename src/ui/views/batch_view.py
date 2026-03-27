import json
import uuid
from typing import Any, List

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton, QComboBox, QSplitter, QListWidget,
                               QAbstractItemView, QProgressBar, QTextEdit, QMessageBox, QListWidgetItem)
from jinja2 import Template

from src.database.models import db, DeckModel, NoteTypeModel, NoteModel, CardModel, PipelineModel, PipelineStepModel, \
    NoteVersionModel, DocumentModel


class BatchWorker(QThread):
    """Thread de traitement par lots. Exécute l'IA et sauvegarde en BDD."""
    progress_val = Signal(int)
    progress_text = Signal(str)
    log = Signal(str)
    finished = Signal(int, int)  # (succès, erreurs)
    error = Signal(str)

    def __init__(self, ai_provider: Any, doc_ids: List[int], deck_id: int, model_id: int, pipeline_id: int):
        super().__init__()
        self.ai_provider = ai_provider
        self.doc_ids = doc_ids
        self.deck_id = deck_id
        self.model_id = model_id
        self.pipeline_id = pipeline_id

    def _clean_json(self, raw_text: str) -> str:
        clean = raw_text.strip()
        if clean.startswith("```json"):
            clean = clean[7:-3].strip()
        elif clean.startswith("```"):
            clean = clean[3:-3].strip()
        return clean

    def run(self) -> None:
        try:
            # 1. Chargement des objets métiers (depuis le thread pour éviter les conflits)
            deck = DeckModel.get_by_id(self.deck_id)
            note_type = NoteTypeModel.get_by_id(self.model_id)
            pipeline = PipelineModel.get_by_id(self.pipeline_id)
            steps = list(pipeline.steps.order_by(PipelineStepModel.step_order))

            fields = json.loads(note_type.fields_schema) if note_type.fields_schema else ["Front", "Back"]
            fields_str = '", "'.join(fields)
            first_field = fields[0] if len(fields) > 0 else 'Field1'
            second_field = fields[1] if len(fields) > 1 else 'Field2'
            templates = json.loads(note_type.templates) if note_type.templates else []

            total_docs = len(self.doc_ids)
            success_count = 0
            error_count = 0

            self.progress_val.emit(0)

            # 2. Boucle Principale sur les documents
            for i, doc_id in enumerate(self.doc_ids):
                doc = DocumentModel.get_by_id(doc_id)
                self.progress_text.emit(f"Traitement du document {i + 1}/{total_docs} : {doc.title}...")
                self.log.emit(f"\n{'=' * 40}\n📄 DEBUT : {doc.title}\n{'=' * 40}")

                current_input = f"TEXTE SOURCE :\n{doc.content}"
                cleaned_output = ""
                doc_failed = False

                # 3. Exécution du Pipeline IA
                for step_idx, step in enumerate(steps, 1):
                    agent = step.agent
                    self.log.emit(f"🤖 Étape {step_idx} : Agent '{agent.name}' en action...")

                    jinja_template = Template(agent.system_prompt)
                    system_prompt = jinja_template.render(
                        fields_str=fields_str, first_field=first_field, second_field=second_field
                    )

                    try:
                        raw_response = self.ai_provider.generate(system_prompt=system_prompt, user_prompt=current_input)
                        cleaned_output = self._clean_json(raw_response)
                        current_input = f"Voici les données à traiter :\n{cleaned_output}"
                    except Exception as e:
                        self.log.emit(f"❌ ERREUR IA sur '{doc.title}': {str(e)}")
                        doc_failed = True
                        break  # On arrête le pipeline pour ce document

                if doc_failed:
                    error_count += 1
                    continue

                # 4. Sauvegarde Directe en Base de Données
                try:
                    data = json.loads(cleaned_output)
                    notes_to_create = data.get("notes", [])

                    if not notes_to_create:
                        raise ValueError("Le JSON ne contient aucune note (liste vide).")

                    # Opération atomique (très rapide) grâce au WAL mode !
                    with db.atomic():
                        for note_data in notes_to_create:
                            # Conteneur
                            note = NoteModel.create(
                                guid=str(uuid.uuid4())[:10],
                                note_type=note_type,
                                tags=json.dumps(["AnkiForge_Batch"]),
                                status="new"
                            )
                            # Version 1
                            NoteVersionModel.create(
                                note=note,
                                version_number=1,
                                content=json.dumps(note_data, ensure_ascii=False),
                                source="ai_batch",
                                is_active=True
                            )
                            # Cartes (Recto/Verso)
                            for idx, tmpl in enumerate(templates):
                                CardModel.create(note=note, deck=deck, template_index=idx)

                    self.log.emit(
                        f"✅ SUCCÈS : {len(notes_to_create)} cartes générées et sauvegardées pour '{doc.title}'.")
                    success_count += 1

                except json.JSONDecodeError:
                    self.log.emit(f"❌ ERREUR JSON : Le format généré n'est pas valide pour '{doc.title}'.")
                    error_count += 1
                except Exception as e:
                    self.log.emit(f"❌ ERREUR BDD : Impossible de sauvegarder '{doc.title}': {str(e)}")
                    error_count += 1

                # Mise à jour de la barre
                progress_pct = int(((i + 1) / total_docs) * 100)
                self.progress_val.emit(progress_pct)

            self.finished.emit(success_count, error_count)

        except Exception as e:
            self.error.emit(f"Erreur fatale du BatchWorker : {str(e)}")


class BatchTab(QWidget):
    """Interface utilisateur pour le traitement par lots (Batch Processing)."""

    def __init__(self, ai_manager: Any) -> None:
        super().__init__()
        self.ai_manager = ai_manager

        layout = QVBoxLayout(self)

        # 1. En-tête (Titre et instructions)
        header = QLabel(
            "<b>⚙️ Automatisation : Traitement par Lots</b><br>Sélectionnez plusieurs documents pour générer des cartes en arrière-plan.")
        header.setStyleSheet("font-size: 16px; margin-bottom: 10px;")
        layout.addWidget(header)

        # 2. Séparateur principal (Gauche: Liste des Docs | Droite: Paramètres et Logs)
        main_splitter = QSplitter(Qt.Horizontal)

        # --- PANNEAU GAUCHE : SÉLECTION DES DOCUMENTS ---
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        left_layout.addWidget(QLabel("<b>📄 1. Sélectionner les cours (Ctrl+Clic) :</b>"))

        self.doc_list = QListWidget()
        self.doc_list.setSelectionMode(QAbstractItemView.ExtendedSelection)  # Permet la sélection multiple !
        self.doc_list.setAlternatingRowColors(True)
        self.doc_list.itemSelectionChanged.connect(self.check_ready_state)
        left_layout.addWidget(self.doc_list)

        self.btn_refresh_docs = QPushButton("🔄 Actualiser la liste")
        self.btn_refresh_docs.clicked.connect(self.load_documents)
        left_layout.addWidget(self.btn_refresh_docs)

        # --- PANNEAU DROIT : PARAMÈTRES ET CONSOLE ---
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        params_layout = QHBoxLayout()

        # Sélecteurs (identiques à creation_view)
        vbox_deck = QVBoxLayout()
        vbox_deck.addWidget(QLabel("<b>📂 Paquet de destination :</b>"))
        self.deck_selector = QComboBox()
        vbox_deck.addWidget(self.deck_selector)
        params_layout.addLayout(vbox_deck)

        vbox_model = QVBoxLayout()
        vbox_model.addWidget(QLabel("<b>🎨 Modèle Anki :</b>"))
        self.model_selector = QComboBox()
        vbox_model.addWidget(self.model_selector)
        params_layout.addLayout(vbox_model)

        vbox_pipe = QVBoxLayout()
        vbox_pipe.addWidget(QLabel("<b>🧠 Pipeline IA :</b>"))
        self.pipeline_selector = QComboBox()
        vbox_pipe.addWidget(self.pipeline_selector)
        params_layout.addLayout(vbox_pipe)

        right_layout.addLayout(params_layout)

        # Console de logs
        right_layout.addWidget(QLabel("<b>🕵️ Console de Suivi :</b>"))
        self.console_log = QTextEdit()
        self.console_log.setReadOnly(True)
        self.console_log.setStyleSheet(
            "background-color: #1e1e1e; color: #d4d4d4; font-family: 'Consolas', 'Courier New', Courier, monospace; padding: 5px;")
        right_layout.addWidget(self.console_log)

        # Barre de progression et Bouton
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        right_layout.addWidget(self.progress_bar)

        self.lbl_status = QLabel("Prêt.")
        right_layout.addWidget(self.lbl_status)

        self.btn_start = QPushButton("🚀 Lancer l'Automatisation")
        self.btn_start.setStyleSheet(
            "background-color: #673AB7; color: white; font-weight: bold; padding: 12px; font-size: 14px;")
        self.btn_start.setEnabled(False)
        self.btn_start.clicked.connect(self.start_batch)
        right_layout.addWidget(self.btn_start)

        # Ajout au splitter
        main_splitter.addWidget(left_panel)
        main_splitter.addWidget(right_panel)
        main_splitter.setSizes([300, 700])

        layout.addWidget(main_splitter)

        # Initialisation
        self.refresh_selectors()
        self.load_documents()

    def load_documents(self) -> None:
        self.doc_list.clear()
        for doc in DocumentModel.select().order_by(DocumentModel.created_at.desc()):
            item = QListWidgetItem(f"📄 {doc.title}")
            item.setData(Qt.UserRole, doc.id)
            self.doc_list.addItem(item)
        self.check_ready_state()

    def refresh_selectors(self) -> None:
        self.deck_selector.clear()
        for deck in DeckModel.select().order_by(DeckModel.name):
            self.deck_selector.addItem(deck.name, userData=deck.id)

        self.model_selector.clear()
        for nt in NoteTypeModel.select().order_by(NoteTypeModel.name):
            self.model_selector.addItem(nt.name, userData=nt.id)

        self.pipeline_selector.clear()
        for pipe in PipelineModel.select().order_by(PipelineModel.name):
            self.pipeline_selector.addItem(pipe.name, userData=pipe.id)

    def check_ready_state(self) -> None:
        """Active le bouton seulement si au moins un document est sélectionné."""
        selected_items = self.doc_list.selectedItems()
        self.btn_start.setEnabled(len(selected_items) > 0)
        self.lbl_status.setText(f"{len(selected_items)} document(s) sélectionné(s).")

    def append_log(self, text: str) -> None:
        self.console_log.append(text)
        # Scroll automatique vers le bas
        scrollbar = self.console_log.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def start_batch(self) -> None:
        selected_items = self.doc_list.selectedItems()
        if not selected_items:
            return

        doc_ids = [item.data(Qt.UserRole) for item in selected_items]
        deck_id = self.deck_selector.currentData()
        model_id = self.model_selector.currentData()
        pipeline_id = self.pipeline_selector.currentData()

        # Sécurités
        if not deck_id or not model_id or not pipeline_id:
            QMessageBox.warning(self, "Erreur", "Veuillez sélectionner un Paquet, un Modèle et un Pipeline.")
            return

        # Verrouillage de l'UI
        self.btn_start.setEnabled(False)
        self.btn_start.setText("⏳ Traitement en cours...")
        self.doc_list.setEnabled(False)
        self.console_log.clear()
        self.progress_bar.setValue(0)

        self.append_log(f"🚀 Démarrage du Batch Processing pour {len(doc_ids)} document(s).")
        self.append_log(f"🧠 IA actuelle : {self.ai_manager.provider.model_name}\n")

        # Lancement du Thread
        self.worker = BatchWorker(
            ai_provider=self.ai_manager.provider,
            doc_ids=doc_ids,
            deck_id=deck_id,
            model_id=model_id,
            pipeline_id=pipeline_id
        )
        self.worker.progress_val.connect(self.progress_bar.setValue)
        self.worker.progress_text.connect(self.lbl_status.setText)
        self.worker.log.connect(self.append_log)
        self.worker.finished.connect(self.on_batch_finished)
        self.worker.error.connect(self.on_batch_error)

        self.worker.start()

    def on_batch_finished(self, success_count: int, error_count: int) -> None:
        self.btn_start.setEnabled(True)
        self.btn_start.setText("🚀 Lancer l'Automatisation")
        self.doc_list.setEnabled(True)
        self.lbl_status.setText("Terminé.")

        msg = f"Traitement terminé.\n\n✅ Succès : {success_count} documents traités.\n❌ Erreurs : {error_count} documents échoués."
        self.append_log(f"\n{'=' * 40}\n{msg}")
        QMessageBox.information(self, "Bilan de l'Automatisation", msg)

    def on_batch_error(self, error_msg: str) -> None:
        self.btn_start.setEnabled(True)
        self.btn_start.setText("🚀 Lancer l'Automatisation")
        self.doc_list.setEnabled(True)
        self.lbl_status.setText("Erreur fatale.")
        QMessageBox.critical(self, "Erreur Fatale", error_msg)
import json
import uuid
from jinja2 import Template
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QTextEdit, QPushButton, QComboBox, QTableWidget,
                               QTableWidgetItem, QMessageBox, QSplitter, QAbstractItemView)
from PySide6.QtWebEngineWidgets import QWebEngineView

from src.database.models import db, DeckModel, NoteTypeModel, NoteModel, CardModel, PipelineModel,PipelineStepModel
from src.utils.anki_renderer import render_anki_card

class GenerationThread(QThread):
    # Signaux pour communiquer avec l'interface graphique
    finished = Signal(list)  # Renvoie la liste des dictionnaires (les notes)
    error = Signal(str)  # En cas de crash
    progress = Signal(str)  # Pour dire "Génération en cours..."

    def __init__(self, ai_provider, text_source: str, note_type: NoteTypeModel, pipeline_id: int):
        super().__init__()
        self.ai_provider = ai_provider
        self.text_source = text_source
        self.note_type = note_type
        self.pipeline_id = pipeline_id

    def _clean_json(self, raw_text: str) -> str:
        """Nettoie le markdown pour garantir du JSON pur entre chaque agent."""
        clean = raw_text.strip()
        if clean.startswith("```json"):
            clean = clean[7:-3].strip()
        elif clean.startswith("```"):
            clean = clean[3:-3].strip()
        return clean

    def run(self):
        try:
            # 1. Chargement du Pipeline
            pipeline = PipelineModel.get_by_id(self.pipeline_id)
            steps = list(pipeline.steps.order_by(PipelineStepModel.step_order))

            if not steps:
                raise ValueError(f"Le pipeline '{pipeline.name}' ne contient aucun agent !")

            # 2. Préparation des variables pour Jinja2
            fields = json.loads(self.note_type.fields_schema) if self.note_type.fields_schema else ["Front", "Back"]
            fields_str = '", "'.join(fields)
            first_field = fields[0] if len(fields) > 0 else 'Field1'
            second_field = fields[1] if len(fields) > 1 else 'Field2'

            # Le premier input est le texte brut de l'utilisateur
            current_input = f"TEXTE SOURCE :\n{self.text_source}"
            total_steps = len(steps)
            cleaned_output = ""

            # ==========================================
            # 🔄 LA BOUCLE MULTI-AGENTS
            # ==========================================
            for i, step in enumerate(steps, 1):
                agent = step.agent
                self.progress.emit(f"Étape {i}/{total_steps} : {agent.name}...")

                # Compilation du prompt de la BDD avec Jinja2
                jinja_template = Template(agent.system_prompt)
                system_prompt = jinja_template.render(
                    fields_str=fields_str,
                    first_field=first_field,
                    second_field=second_field
                )

                # Appel à l'IA
                raw_response = self.ai_provider.generate(
                    system_prompt=system_prompt,
                    user_prompt=current_input
                )

                # On nettoie pour que le JSON soit parfait
                cleaned_output = self._clean_json(raw_response)

                # 🧠 MAGIE : La sortie de cet agent devient l'entrée du suivant !
                current_input = f"Voici les données à traiter (provenant de l'étape précédente) :\n{cleaned_output}"

            # ==========================================
            # 🏁 PARSING FINAL (Après le dernier agent)
            # ==========================================
            data = json.loads(cleaned_output)
            if "notes" not in data:
                raise ValueError("Le JSON final ne contient pas la clé 'notes'.")

            self.finished.emit(data["notes"])

        except json.JSONDecodeError as e:
            self.error.emit(
                f"L'un des agents a brisé le format JSON.\nErreur : {e}\n\nDernière sortie:\n{cleaned_output[:200]}")
        except Exception as e:
            self.error.emit(f"Erreur lors du pipeline IA : {str(e)}")

class CreationTab(QWidget):
    def __init__(self, ai_provider, prompt_manager=None):
        super().__init__()
        self.ai_provider = ai_provider
        self.generated_notes = []

        layout = QVBoxLayout(self)

        # --- 1. PARAMÈTRES (En Haut) ---
        params_layout = QHBoxLayout()

        params_layout.addWidget(QLabel("<b>📂 Paquet :</b>"))
        self.deck_selector = QComboBox()
        params_layout.addWidget(self.deck_selector)

        params_layout.addWidget(QLabel("   <b>🎨 Modèle :</b>"))
        self.model_selector = QComboBox()
        self.model_selector.currentIndexChanged.connect(self.on_model_changed)
        params_layout.addWidget(self.model_selector)

        # --- NOUVEAU : SÉLECTEUR DE PIPELINE ---
        params_layout.addWidget(QLabel("   <b>🧠 Pipeline IA :</b>"))
        self.pipeline_selector = QComboBox()
        params_layout.addWidget(self.pipeline_selector)

        params_layout.addStretch()
        layout.addLayout(params_layout)

        # --- 2. SPLITTER HAUT/BAS ---
        main_splitter = QSplitter(Qt.Vertical)

        # A. Zone de texte Source
        source_widget = QWidget()
        source_layout = QVBoxLayout(source_widget)
        source_layout.setContentsMargins(0, 0, 0, 0)
        source_layout.addWidget(QLabel("<b>📝 Texte Source (Cours, Article, etc.) :</b>"))
        self.source_text = QTextEdit()
        source_layout.addWidget(self.source_text)

        self.btn_generate = QPushButton("✨ Générer les Cartes")
        self.btn_generate.setStyleSheet(
            "background-color: #4CAF50; color: white; font-weight: bold; padding: 10px;")
        self.btn_generate.clicked.connect(self.start_generation)
        source_layout.addWidget(self.btn_generate)

        # B. Zone des Résultats (Bas)
        bottom_splitter = QSplitter(Qt.Horizontal)

        # B1. Tableau
        table_container = QWidget()
        table_layout = QVBoxLayout(table_container)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.addWidget(QLabel("<b>✅ Aperçu (Double-cliquez pour éditer) :</b>"))

        self.results_table = QTableWidget()
        self.results_table.horizontalHeader().setStretchLastSection(True)
        self.results_table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.results_table.setAlternatingRowColors(True)
        self.results_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.results_table.setSelectionMode(QAbstractItemView.SingleSelection)

        self.results_table.itemChanged.connect(self.on_table_item_changed)
        self.results_table.itemSelectionChanged.connect(self.update_preview)

        table_layout.addWidget(self.results_table)

        self.btn_save = QPushButton("💾 Sauvegarder dans la base de données")
        self.btn_save.setStyleSheet("background-color: #2196F3; color: white; font-weight: bold; padding: 8px;")
        self.btn_save.clicked.connect(self.save_to_database)
        self.btn_save.setEnabled(False)
        table_layout.addWidget(self.btn_save)

        # B2. Preview Web
        preview_container = QWidget()
        preview_layout = QVBoxLayout(preview_container)
        preview_layout.setContentsMargins(0, 0, 0, 0)

        controls_layout = QHBoxLayout()
        self.preview_card_selector = QComboBox()
        self.preview_card_selector.currentIndexChanged.connect(self.update_preview)

        self.preview_side_selector = QComboBox()
        self.preview_side_selector.addItems(["Voir Recto", "Voir Verso"])
        self.preview_side_selector.currentIndexChanged.connect(self.update_preview)

        controls_layout.addWidget(self.preview_card_selector)
        controls_layout.addWidget(self.preview_side_selector)
        preview_layout.addLayout(controls_layout)

        self.web_view = QWebEngineView()
        preview_layout.addWidget(self.web_view)

        bottom_splitter.addWidget(table_container)
        bottom_splitter.addWidget(preview_container)
        bottom_splitter.setSizes([450, 350])

        main_splitter.addWidget(source_widget)
        main_splitter.addWidget(bottom_splitter)
        main_splitter.setSizes([200, 500])

        layout.addWidget(main_splitter)
        self.refresh_selectors()

    def refresh_selectors(self):
        self.deck_selector.clear()
        for deck in DeckModel.select().order_by(DeckModel.name):
            self.deck_selector.addItem(deck.name, userData=deck.id)

        self.model_selector.clear()
        for nt in NoteTypeModel.select().order_by(NoteTypeModel.name):
            self.model_selector.addItem(nt.name, userData=nt.id)

        # Chargement des Pipelines
        self.pipeline_selector.clear()
        for pipe in PipelineModel.select().order_by(PipelineModel.name):
            self.pipeline_selector.addItem(pipe.name, userData=pipe.id)

    def on_model_changed(self):
        model_id = self.model_selector.currentData()
        if not model_id: return

        note_type = NoteTypeModel.get_by_id(model_id)
        fields = json.loads(note_type.fields_schema) if note_type.fields_schema else []

        self.results_table.blockSignals(True)
        self.results_table.clear()
        self.results_table.setColumnCount(len(fields))
        self.results_table.setHorizontalHeaderLabels(fields)
        self.results_table.setRowCount(0)
        self.results_table.blockSignals(False)

        self.preview_card_selector.blockSignals(True)
        self.preview_card_selector.clear()
        templates = json.loads(note_type.templates) if note_type.templates else []
        for tmpl in templates:
            self.preview_card_selector.addItem(tmpl.get("name", "Carte"))
        self.preview_card_selector.blockSignals(False)
        self.update_preview()

    def start_generation(self):
        text = self.source_text.toPlainText()
        model_id = self.model_selector.currentData()
        pipeline_id = self.pipeline_selector.currentData()

        if not text.strip():
            QMessageBox.warning(self, "Erreur", "Veuillez entrer du texte source.")
            return

        if not pipeline_id:
            QMessageBox.warning(self, "Erreur", "Veuillez sélectionner un Pipeline IA.")
            return

        note_type = NoteTypeModel.get_by_id(model_id)

        self.btn_generate.setEnabled(False)
        self.results_table.setRowCount(0)
        self.web_view.setHtml("")

        # Lancement avec l'ID du pipeline
        self.thread = GenerationThread(self.ai_provider, text, note_type, pipeline_id)
        self.thread.progress.connect(self.update_progress)
        self.thread.finished.connect(self.on_generation_success)
        self.thread.error.connect(self.on_generation_error)
        self.thread.start()

    def update_progress(self, message):
        """Affiche l'étape en cours sur le bouton"""
        self.btn_generate.setText(message)

    def on_generation_success(self, generated_notes):
        self.generated_notes = generated_notes
        self.btn_generate.setEnabled(True)
        self.btn_generate.setText("✨ Regénérer les Cartes")
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

    def on_generation_error(self, error_msg):
        self.btn_generate.setEnabled(True)
        self.btn_generate.setText("✨ Générer les Cartes")
        QMessageBox.critical(self, "Erreur IA", error_msg)

    def on_table_item_changed(self, item):
        row = item.row()
        col = item.column()
        field_name = self.results_table.horizontalHeaderItem(col).text()

        if 0 <= row < len(self.generated_notes):
            self.generated_notes[row][field_name] = item.text()
            selected_items = self.results_table.selectedItems()
            if selected_items and selected_items[0].row() == row:
                self.update_preview()

    def update_preview(self):
        selected_items = self.results_table.selectedItems()
        if not selected_items or not self.generated_notes:
            self.web_view.setHtml("")
            return

        row = selected_items[0].row()
        if row >= len(self.generated_notes):
            return

        current_data = self.generated_notes[row]
        model_id = self.model_selector.currentData()
        note_type = NoteTypeModel.get_by_id(model_id)

        templates = json.loads(note_type.templates) if note_type.templates else []
        selected_tmpl_idx = self.preview_card_selector.currentIndex()
        if selected_tmpl_idx < 0 or selected_tmpl_idx >= len(templates):
            return

        tmpl = templates[selected_tmpl_idx]
        is_recto = self.preview_side_selector.currentIndex() == 0

        raw_html = tmpl.get("qfmt", "") if is_recto else tmpl.get("afmt", "")
        css = note_type.css_style if note_type.css_style else ""

        final_html = render_anki_card(
            raw_html=raw_html,
            css=css,
            fields_dict=current_data,
            is_recto=is_recto,
            front_html=tmpl.get("qfmt", "")
        )
        self.web_view.setHtml(final_html)

    def save_to_database(self):
        if not self.generated_notes: return

        deck_id = self.deck_selector.currentData()
        model_id = self.model_selector.currentData()
        deck = DeckModel.get_by_id(deck_id)
        note_type = NoteTypeModel.get_by_id(model_id)
        templates = json.loads(note_type.templates) if note_type.templates else []

        try:
            with db.atomic():
                for note_data in self.generated_notes:
                    note = NoteModel.create(
                        guid=str(uuid.uuid4())[:10],
                        note_type=note_type,
                        content=json.dumps(note_data, ensure_ascii=False),
                        tags=json.dumps(["AnkiForge_AI"]),
                        status="new"
                    )
                    for idx, tmpl in enumerate(templates):
                        CardModel.create(note=note, deck=deck, template_index=idx)

            QMessageBox.information(self, "Succès",
                                    f"{len(self.generated_notes)} notes créées dans '{deck.name}' !")
            self.generated_notes.clear()
            self.results_table.setRowCount(0)
            self.web_view.setHtml("")
            self.btn_save.setEnabled(False)
            self.source_text.clear()

        except Exception as e:
            QMessageBox.critical(self, "Erreur Base de Données", f"Impossible de sauvegarder : {e}")


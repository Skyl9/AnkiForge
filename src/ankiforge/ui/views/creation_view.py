import json
import uuid
from typing import Any, List, Dict

import qtawesome as qta
from PySide6.QtCore import Qt, QThread, Signal, QUrl, Slot
from PySide6.QtGui import QShortcut, QKeySequence
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QTextEdit, QComboBox, QTableWidget,
                               QTableWidgetItem, QMessageBox, QSplitter, QAbstractItemView, QTabWidget, QGroupBox,
                               QProgressBar)
from jinja2 import Template

from ankiforge.database.models import db, DeckModel, NoteTypeModel, NoteModel, CardModel, PipelineModel, \
    PipelineStepModel, \
    NoteVersionModel, DocumentModel, LLMConfigModel
from ankiforge.services.ai.utils import parse_ai_json_response
from ankiforge.ui.components.components import ActionButton, PrimaryButton
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.anki_renderer import render_anki_card
from ankiforge.utils.paths import get_app_data_dir


class GenerationThread(QThread):
    finished = Signal(list)
    error = Signal(str)
    progress = Signal(str)
    log = Signal(str)

    def __init__(self, ai_provider: Any, text_source: str, note_type_id: int, pipeline_id: int) -> None:
        super().__init__()
        self.ai_provider = ai_provider
        self.text_source = text_source
        self.note_type_id = note_type_id
        self.pipeline_id = pipeline_id

    @staticmethod
    def _clean_json(raw_text: str) -> str:
        clean = raw_text.strip()
        if clean.startswith("```json"):
            clean = clean[7:-3].strip()
        elif clean.startswith("```"):
            clean = clean[3:-3].strip()
        return clean

    def run(self) -> None:
        try:
            pipeline = PipelineModel.get_by_id(self.pipeline_id)
            note_type = NoteTypeModel.get_by_id(self.note_type_id)

            steps = list(pipeline.steps.order_by(PipelineStepModel.step_order))

            if not steps:
                raise ValueError(f"Le pipeline '{pipeline.name}' ne contient aucun agent !")

            fields = json.loads(note_type.fields_schema) if note_type.fields_schema else ["Front", "Back"]
            fields_str = '", "'.join(fields)

            first_field = fields[0] if len(fields) > 0 else 'Field1'
            second_field = fields[1] if len(fields) > 1 else 'Field2'

            current_input = f"TEXTE SOURCE :\n{self.text_source}"
            total_steps = len(steps)
            cleaned_output = ""

            for i, step in enumerate(steps, 1):
                agent = step.agent
                self.progress.emit(f"Étape {i}/{total_steps} : {agent.name}...")

                jinja_template = Template(agent.system_prompt)
                system_prompt = jinja_template.render(fields_str=fields_str, first_field=first_field,
                                                      second_field=second_field)

                self.log.emit(f"--- 🤖 DÉBUT ÉTAPE {i} : {agent.name.upper()} ---\n")
                self.log.emit(f"🔵 PROMPT SYSTÈME :\n{system_prompt}\n")
                self.log.emit(f"🟢 ENTRÉE UTILISATEUR :\n{current_input}\n")

                raw_response = self.ai_provider.generate(system_prompt=system_prompt, user_prompt=current_input)

                self.log.emit(f"🟠 RÉPONSE BRUTE DE L'IA :\n{raw_response}\n\n")

                cleaned_output = self._clean_json(raw_response)
                current_input = f"Voici les données à traiter (provenant de l'étape précédente) :\n{cleaned_output}"

            data = parse_ai_json_response(raw_response)

            if "notes" not in data:
                raise ValueError("Le JSON final ne contient pas la clé 'notes'.")

            self.finished.emit(data["notes"])

        except json.JSONDecodeError as e:
            self.error.emit(
                f"L'un des agents a brisé le format JSON.\nErreur : {e}\n\nDernière sortie:\n{cleaned_output[:200]}")
        except Exception as e:
            self.error.emit(f"Erreur lors du pipeline IA : {str(e)}")


class CreationTab(QWidget):
    def __init__(self, ai_manager: Any) -> None:
        super().__init__()
        self.ai_manager = ai_manager
        self.generated_notes: List[Dict[str, str]] = []

        layout = QVBoxLayout(self)

        # --- NOUVEAU : Bloc 1 - Paramètres IA et Destination ---
        params_group = QGroupBox("1. Configuration de l'IA et Destination")
        params_layout = QHBoxLayout(params_group)

        params_layout.addWidget(QLabel("<b>Paquet :</b>"))
        self.deck_selector = QComboBox()
        params_layout.addWidget(self.deck_selector)

        params_layout.addWidget(QLabel("   <b>Modèle de carte :</b>"))
        self.model_selector = QComboBox()
        self.model_selector.currentIndexChanged.connect(self.on_model_changed)
        params_layout.addWidget(self.model_selector)

        params_layout.addWidget(QLabel("   <b>Moteur IA :</b>"))
        self.llm_selector = QComboBox()
        self.llm_selector.currentIndexChanged.connect(self.update_token_estimate)
        params_layout.addWidget(self.llm_selector)

        params_layout.addWidget(QLabel("   <b>Pipeline IA :</b>"))
        self.pipeline_selector = QComboBox()
        params_layout.addWidget(self.pipeline_selector)

        layout.addWidget(params_group)

        # Standard Qt6 : Qt.Orientation.Vertical
        main_splitter = QSplitter(Qt.Orientation.Vertical)

        # --- Bloc 2 - Source de données ---
        source_group = QGroupBox("2. Texte Source")
        source_layout = QVBoxLayout(source_group)

        source_header = QHBoxLayout()
        source_header.addWidget(QLabel("<b>Choisir un cours :</b>"))
        self.doc_selector = QComboBox()
        self.doc_selector.currentIndexChanged.connect(self.on_document_changed)
        source_header.addWidget(self.doc_selector, stretch=1)

        self.btn_refresh_docs = ActionButton(qta.icon('fa5s.sync'), "")
        self.btn_refresh_docs.clicked.connect(self.load_documents)
        source_header.addWidget(self.btn_refresh_docs)

        source_header.addWidget(QLabel("<b>Partie :</b>"))
        self.section_selector = QComboBox()
        self.section_selector.currentIndexChanged.connect(self.on_section_changed)
        source_header.addWidget(self.section_selector, stretch=1)

        source_layout.addLayout(source_header)

        self.source_text = QTextEdit()
        self.source_text.setPlaceholderText("Sélectionnez un document puis une section...")
        self.source_text.textChanged.connect(self.update_token_estimate)  # 👈 Connexion au texte
        source_layout.addWidget(self.source_text)

        token_layout = QHBoxLayout()
        self.token_label = QLabel("<b>Tokens : 0 / ?</b>")
        self.token_bar = QProgressBar()
        self.token_bar.setTextVisible(False)
        self.token_bar.setFixedHeight(8)
        token_layout.addWidget(self.token_label)
        token_layout.addWidget(self.token_bar, stretch=1)
        source_layout.addLayout(token_layout)

        self.btn_generate = PrimaryButton(qta.icon('fa5s.magic', color='white'), " Générer les Cartes")
        self.btn_generate.clicked.connect(self.start_generation)
        source_layout.addWidget(self.btn_generate)

        # --- Bloc 3 : Résultats ---
        # Standard Qt6 : Qt.Orientation.Horizontal
        bottom_splitter = QSplitter(Qt.Orientation.Horizontal)

        table_container = QWidget()
        table_layout = QVBoxLayout(table_container)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.addWidget(QLabel("<b>Aperçu (Double-cliquez pour éditer) :</b>"))

        self.results_table = QTableWidget()
        self.results_table.horizontalHeader().setStretchLastSection(True)
        # Standards Qt6
        self.results_table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.EditKeyPressed)
        self.results_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.results_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.results_table.setAlternatingRowColors(True)
        self.results_table.itemChanged.connect(self.on_table_item_changed)
        self.results_table.itemSelectionChanged.connect(self.update_preview)
        table_layout.addWidget(self.results_table)

        self.btn_save = PrimaryButton(qta.icon('fa5s.save', color='white'), " Sauvegarder dans la base de données")
        self.btn_save.clicked.connect(self.save_to_database)
        self.btn_save.setEnabled(False)
        table_layout.addWidget(self.btn_save)

        right_tabs = QTabWidget()
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
        self.web_view.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)

        preview_layout.addWidget(self.web_view)

        # Icônes pour les onglets
        right_tabs.addTab(preview_container, qta.icon('fa5s.eye'), " Aperçu de la Carte")

        self.console_log = QTextEdit()
        self.console_log.setReadOnly(True)
        self.console_log.setStyleSheet("background-color: #1e1e1e; color: #00FF00; font-family: 'Consolas', monospace;")
        right_tabs.addTab(self.console_log, qta.icon('fa5s.terminal'), " Console IA (Logs)")

        bottom_splitter.addWidget(table_container)
        bottom_splitter.addWidget(right_tabs)
        bottom_splitter.setSizes([450, 350])

        main_splitter.addWidget(source_group)
        main_splitter.addWidget(bottom_splitter)
        main_splitter.setSizes([200, 500])

        layout.addWidget(main_splitter)

        self.refresh_selectors()
        self.load_documents()

        # --- RACCOURCIS CLAVIER ---
        # Ctrl+Enter (ou Ctrl+Retour) pour lancer la génération
        self.shortcut_generate = QShortcut(QKeySequence("Ctrl+Return"), self)
        self.shortcut_generate.activated.connect(self.start_generation)

        # Ctrl+S pour sauvegarder dans la base (une fois généré)
        self.shortcut_save_db = QShortcut(QKeySequence("Ctrl+S"), self)
        self.shortcut_save_db.activated.connect(self.save_to_database)

    @Slot()
    def refresh_data(self) -> None:
        """Méthode standardisée appelée par la MainWindow au changement d'onglet."""
        self.refresh_selectors()
        self.load_documents()

    @Slot()
    def refresh_selectors(self) -> None:
        """Met à jour les listes déroulantes IA et Modèles."""
        self.deck_selector.blockSignals(True)
        self.model_selector.blockSignals(True)
        self.pipeline_selector.blockSignals(True)
        self.llm_selector.blockSignals(True)

        # On sauvegarde la sélection actuelle pour la remettre après
        current_deck = self.deck_selector.currentData()
        current_model = self.model_selector.currentData()
        current_pipe = self.pipeline_selector.currentData()
        current_llm = self.llm_selector.currentData()

        self.deck_selector.clear()
        for deck in DeckModel.select().order_by(DeckModel.name):
            self.deck_selector.addItem(deck.name, userData=deck.id)

        self.model_selector.clear()
        for nt in NoteTypeModel.select().order_by(NoteTypeModel.name):
            self.model_selector.addItem(nt.name, userData=nt.id)

        self.pipeline_selector.clear()
        for pipe in PipelineModel.select().order_by(PipelineModel.name):
            self.pipeline_selector.addItem(pipe.name, userData=pipe.id)

            self.llm_selector.clear()
            for llm in LLMConfigModel.select().order_by(LLMConfigModel.display_name):
                self.llm_selector.addItem(llm.display_name, userData=llm.id)
            if current_llm: self.llm_selector.setCurrentIndex(self.llm_selector.findData(current_llm))
            self.llm_selector.blockSignals(False)

        # On remet les sélections
        if current_deck: self.deck_selector.setCurrentIndex(self.deck_selector.findData(current_deck))
        if current_model: self.model_selector.setCurrentIndex(self.model_selector.findData(current_model))
        if current_pipe: self.pipeline_selector.setCurrentIndex(self.pipeline_selector.findData(current_pipe))

        self.deck_selector.blockSignals(False)
        self.model_selector.blockSignals(False)
        self.pipeline_selector.blockSignals(False)

        self.on_model_changed()

    @Slot()
    def update_token_estimate(self) -> None:
        text = self.source_text.toPlainText()
        estimated_tokens = len(text) // 4

        llm_id = self.llm_selector.currentData()
        max_tokens = 8192
        if llm_id:
            try:
                max_tokens = LLMConfigModel.get_by_id(llm_id).context_limit
            except Exception:
                pass

        self.token_bar.setMaximum(max_tokens)
        self.token_bar.setValue(min(estimated_tokens, max_tokens))
        self.token_label.setText(f"<b>Tokens : ~{estimated_tokens:,} / {max_tokens:,}</b>".replace(',', ' '))

        if estimated_tokens < (max_tokens * 0.5):
            color = "#4CAF50"
            self.btn_generate.setText(" Générer les Cartes")
        elif estimated_tokens < (max_tokens * 0.8):
            color = "#FF9800"
            self.btn_generate.setText(" Générer les Cartes (Texte long)")
        else:
            color = "#F44336"
            self.btn_generate.setText(" Générer (Risque de dépassement IA !)")

        self.token_label.setStyleSheet(f"color: {color};")
        self.token_bar.setStyleSheet(f"""
                QProgressBar {{ border: 1px solid palette(alternate-base); border-radius: 4px; background-color: palette(base); }}
                QProgressBar::chunk {{ background-color: {color}; border-radius: 4px; }}
            """)

    @Slot()
    def load_documents(self) -> None:
        """Charge la liste des documents depuis la base de données."""
        self.doc_selector.blockSignals(True)
        self.doc_selector.clear()
        self.doc_selector.addItem("-- Sélectionner un document --", None)

        for doc in DocumentModel.select().order_by(DocumentModel.created_at.desc()):
            self.doc_selector.addItem(doc.title, doc.id)

        self.doc_selector.blockSignals(False)

        # 👇 NOUVEAU : Auto-Sélection du premier document valide au lancement 👇
        if self.doc_selector.count() > 1:
            self.doc_selector.setCurrentIndex(1)

    def _parse_markdown_sections(self, text: str) -> list[tuple[str, str]]:
        sections = []
        current_title = ""
        current_content = []

        for line in text.split('\n'):
            if line.startswith('#'):
                if current_title or current_content:
                    if ''.join(current_content).strip():
                        sections.append(
                            (current_title if current_title else "Introduction", '\n'.join(current_content)))

                clean_title = line.replace('#', '').strip()
                if len(clean_title) > 50: clean_title = clean_title[:47] + "..."
                current_title = clean_title
                current_content = [line]
            else:
                current_content.append(line)

        if current_content and ''.join(current_content).strip():
            sections.append((current_title if current_title else "Texte", '\n'.join(current_content)))

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
            self.section_selector.addItem("📑 Tout le document", full_text)
            for title, content in sections:
                self.section_selector.addItem(f"🔹 {title}", content)

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

    @Slot()
    def start_generation(self) -> None:
        text = self.source_text.toPlainText()
        model_id = self.model_selector.currentData()
        pipeline_id = self.pipeline_selector.currentData()

        if not text.strip():
            QMessageBox.warning(self, "Erreur", "Veuillez entrer du texte source.")
            return
        if not pipeline_id:
            QMessageBox.warning(self, "Erreur", "Veuillez sélectionner un Pipeline IA.")
            return

        self.btn_generate.setEnabled(False)
        self.results_table.setRowCount(0)
        self.web_view.setHtml("")
        self.console_log.clear()

        self.thread = GenerationThread(self.ai_manager.provider, text, model_id, pipeline_id)
        self.thread.progress.connect(self.update_progress)
        self.thread.log.connect(self.append_log)
        self.thread.finished.connect(self.on_generation_success)
        self.thread.error.connect(self.on_generation_error)
        self.thread.start()

    @Slot(str)
    def append_log(self, text: str) -> None:
        self.console_log.append(text)

    @Slot(str)
    def update_progress(self, message: str) -> None:
        self.btn_generate.setText(message)

    @Slot(list)
    def on_generation_success(self, generated_notes: List[Dict[str, str]]) -> None:
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

    @Slot(str)
    def on_generation_error(self, error_msg: str) -> None:
        self.btn_generate.setEnabled(True)
        self.btn_generate.setText("✨ Générer les Cartes")
        QMessageBox.critical(self, "Erreur IA", error_msg)

    @Slot(QTableWidgetItem)
    def on_table_item_changed(self, item: QTableWidgetItem) -> None:
        row = item.row()
        col = item.column()
        field_name = self.results_table.horizontalHeaderItem(col).text()

        if 0 <= row < len(self.generated_notes):
            self.generated_notes[row][field_name] = item.text()
            selected_items = self.results_table.selectedItems()
            if selected_items and selected_items[0].row() == row:
                self.update_preview()

    @Slot()
    def update_preview(self) -> None:
        selected_items = self.results_table.selectedItems()
        if not selected_items or not self.generated_notes:
            self.web_view.setHtml("")
            return

        row = selected_items[0].row()
        if row >= len(self.generated_notes): return

        current_data = self.generated_notes[row]
        model_id = self.model_selector.currentData()
        note_type = NoteTypeModel.get_by_id(model_id)

        templates = json.loads(note_type.templates) if note_type.templates else []
        selected_tmpl_idx = self.preview_card_selector.currentIndex()
        if selected_tmpl_idx < 0 or selected_tmpl_idx >= len(templates): return

        tmpl = templates[selected_tmpl_idx]
        is_recto = self.preview_side_selector.currentIndex() == 0

        raw_html = tmpl.get("qfmt", "") if is_recto else tmpl.get("afmt", "")
        css = note_type.css_style if note_type.css_style else ""

        final_html = render_anki_card(
            raw_html=raw_html, css=css, fields_dict=current_data,
            is_recto=is_recto, front_html=tmpl.get("qfmt", "")
        )

        media_dir = get_app_data_dir() / 'media'
        media_dir.mkdir(exist_ok=True)  # S'assure que le dossier existe

        base_url = QUrl.fromLocalFile(media_dir)

        self.web_view.setHtml(final_html, base_url)

    @Slot()
    def save_to_database(self) -> None:
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
                        guid=str(uuid.uuid4())[:10], note_type=note_type,
                        tags=json.dumps(["AnkiForge_AI"]), status="new"
                    )
                    NoteVersionModel.create(
                        note=note, version_number=1, content=json.dumps(note_data, ensure_ascii=False),
                        source="ai", is_active=True
                    )
                    for idx, tmpl in enumerate(templates):
                        CardModel.create(note=note, deck=deck, template_index=idx)

            show_toast(self, f"{len(self.generated_notes)} notes créées !")
            self.generated_notes.clear()
            self.results_table.setRowCount(0)
            self.web_view.setHtml("")
            self.btn_save.setEnabled(False)

        except Exception as e:
            QMessageBox.critical(self, "Erreur Base de donnée", f"Impossible de sauvegarder : {e}")

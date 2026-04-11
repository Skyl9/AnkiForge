# ruff: noqa: E501
import json
import os
import uuid
from typing import Any

import qtawesome as qta
from PySide6.QtCore import Qt, QThread, Signal, QUrl, Slot
from PySide6.QtGui import QShortcut, QKeySequence, QFont
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QTextEdit,
    QComboBox,
    QTableWidget,
    QTableWidgetItem,
    QMessageBox,
    QSplitter,
    QAbstractItemView,
    QTabWidget,
    QProgressBar,
    QGridLayout,
    QFrame,
)
from jinja2 import Template

from ankiforge.database.models import (
    db,
    DeckModel,
    NoteTypeModel,
    NoteModel,
    CardModel,
    PipelineModel,
    PipelineStepModel,
    NoteVersionModel,
    DocumentModel,
    LLMConfigModel,
)
from ankiforge.services.ai.base import MockProvider, LLMProvider
from ankiforge.services.ai.flexible_service import OllamaProvider, GroqProvider, OpenAICompatibleProvider
from ankiforge.services.ai.gemini_service import GeminiService
from ankiforge.services.ai.utils import parse_ai_json_response
from ankiforge.ui.components.components import ActionButton, PrimaryButton, RoundedPanel, DangerButton
from ankiforge.ui.theme import is_dark_mode
from ankiforge.ui.widgets.cloze_gestion import get_preview_template, sync_preview_card_selector
from ankiforge.ui.widgets.safe_web_preview import SafeWebEngineView
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.anki_renderer import render_anki_card, get_max_cloze_index
from ankiforge.utils.paths import get_app_data_dir


class GenerationThread(QThread):
    finished = Signal(list)
    error = Signal(str)
    progress = Signal(str)
    log = Signal(str)
    cancelled = Signal()

    def __init__(self, ai_provider: Any, text_source: str, note_type_id: int, pipeline_id: int) -> None:
        super().__init__()
        self.ai_provider = ai_provider
        self.text_source = text_source
        self.note_type_id = note_type_id
        self.pipeline_id = pipeline_id
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    @staticmethod
    def _clean_json(raw_text: str) -> str:
        clean = raw_text.strip()
        if clean.startswith("```json"):
            clean = clean[7:-3].strip()
        elif clean.startswith("```"):
            clean = clean[3:-3].strip()
        return clean

    def run(self) -> None:
        cleaned_output = ""
        raw_response = ""
        try:
            pipeline = PipelineModel.get_by_id(self.pipeline_id)
            note_type = NoteTypeModel.get_by_id(self.note_type_id)

            steps = list(pipeline.steps.order_by(PipelineStepModel.step_order))

            if not steps:
                raise ValueError(f"Le pipeline '{pipeline.name}' ne contient aucun agent !")

            fields = json.loads(note_type.fields_schema) if note_type.fields_schema else ["Front", "Back"]
            fields_str = '", "'.join(fields)

            first_field = fields[0] if len(fields) > 0 else "Field1"
            second_field = fields[1] if len(fields) > 1 else "Field2"

            current_input = f"TEXTE SOURCE :\n{self.text_source}"
            total_steps = len(steps)

            for i, step in enumerate(steps, 1):
                if self._is_cancelled:
                    self.log.emit("\n Génération annulée par l'utilisateur.")
                    self.cancelled.emit()
                    return
                agent = step.agent
                self.progress.emit(f"Étape {i}/{total_steps} : {agent.name}...")

                jinja_template = Template(agent.system_prompt)
                system_prompt = jinja_template.render(fields_str=fields_str, first_field=first_field, second_field=second_field)

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
            self.error.emit(f"L'un des agents a brisé le format JSON.\nErreur : {e}\n\nDernière sortie:\n{cleaned_output[:200]}")
        except Exception as e:
            self.error.emit(f"Erreur lors du pipeline IA : {str(e)}")


class CreationTab(QWidget):
    def __init__(self, ai_manager: Any) -> None:
        super().__init__()
        self.thread: GenerationThread | None = None
        self.ai_manager = ai_manager
        self.generated_notes: list[dict[str, str]] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)

        main_splitter = QSplitter(Qt.Orientation.Vertical)
        main_splitter.setHandleWidth(8)
        main_splitter.setChildrenCollapsible(False)

        # ==========================================
        # BLOC HAUT : CONFIGURATION & SOURCE
        # ==========================================

        top_container = QWidget()
        top_layout = QVBoxLayout(top_container)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(15)

        # 1. PARAMÈTRES (Plus aérés)
        params_panel = RoundedPanel()
        params_layout = QVBoxLayout(params_panel)
        params_layout.setContentsMargins(20, 15, 20, 20)

        # Titre de section moderne (Petites majuscules grisées)
        lbl_title_1 = QLabel("1. CONFIGURATION DE L'IA ET DESTINATION")
        lbl_title_1.setStyleSheet("font-weight: bold; color: palette(placeholder-text); font-size: 11px; letter-spacing: 1px;")
        params_layout.addWidget(lbl_title_1)

        params_grid = QGridLayout()
        params_grid.setHorizontalSpacing(30)
        params_grid.setVerticalSpacing(10)

        lbl_style = "color: palette(placeholder-text); font-size: 12px; font-weight: 500;"

        l_deck = QLabel("Paquet de destination :")
        l_deck.setStyleSheet(lbl_style)
        params_grid.addWidget(l_deck, 0, 0)
        self.deck_selector = QComboBox()
        self.deck_selector.setMinimumHeight(32)
        self.deck_selector.setMinimumWidth(100)
        params_grid.addWidget(self.deck_selector, 1, 0)

        l_model = QLabel("Modèle de note (Anki) :")
        l_model.setStyleSheet(lbl_style)
        params_grid.addWidget(l_model, 0, 1)
        self.model_selector = QComboBox()
        self.model_selector.setMinimumHeight(32)
        self.model_selector.setMinimumWidth(100)
        self.model_selector.currentIndexChanged.connect(self.on_model_changed)
        params_grid.addWidget(self.model_selector, 1, 1)

        l_llm = QLabel("Moteur IA :")
        l_llm.setStyleSheet(lbl_style)
        params_grid.addWidget(l_llm, 2, 0)
        self.llm_selector = QComboBox()
        self.llm_selector.setMinimumHeight(32)
        self.llm_selector.setMinimumWidth(100)
        self.llm_selector.currentIndexChanged.connect(self.update_token_estimate)
        params_grid.addWidget(self.llm_selector, 3, 0)

        l_pipe = QLabel("Pipeline de génération :")
        l_pipe.setStyleSheet(lbl_style)
        params_grid.addWidget(l_pipe, 2, 1)
        self.pipeline_selector = QComboBox()
        self.pipeline_selector.setMinimumHeight(32)
        self.pipeline_selector.setMinimumWidth(100)
        params_grid.addWidget(self.pipeline_selector, 3, 1)

        params_layout.addLayout(params_grid)
        layout.addWidget(params_panel)

        # ==========================================
        # BLOC 2 : TEXTE SOURCE (En Carte)
        # ==========================================
        source_panel = RoundedPanel()
        source_layout = QVBoxLayout(source_panel)
        source_layout.setContentsMargins(20, 15, 20, 15)

        source_layout.setSpacing(15)

        lbl_title_2 = QLabel("2. TEXTE SOURCE")
        lbl_title_2.setStyleSheet("font-weight: bold; color: palette(placeholder-text); font-size: 11px; letter-spacing: 1px;")
        source_layout.addWidget(lbl_title_2)

        source_header = QHBoxLayout()
        source_header.addWidget(QLabel("Choisir un cours :"))
        self.doc_selector = QComboBox()
        self.doc_selector.setMinimumWidth(100)
        self.doc_selector.currentIndexChanged.connect(self.on_document_changed)
        source_header.addWidget(self.doc_selector, stretch=1)

        self.btn_refresh_docs = ActionButton("fa5s.sync", "")
        self.btn_refresh_docs.clicked.connect(self.load_documents)
        source_header.addWidget(self.btn_refresh_docs)

        source_header.addWidget(QLabel("Partie :"))
        self.section_selector = QComboBox()
        self.section_selector.setMinimumWidth(100)
        self.section_selector.currentIndexChanged.connect(self.on_section_changed)
        source_header.addWidget(self.section_selector, stretch=1)

        source_layout.addLayout(source_header)

        self.source_text = QTextEdit()
        self.source_text.setPlaceholderText("Sélectionnez un document puis une section...")
        self.source_text.textChanged.connect(self.update_token_estimate)
        source_layout.addWidget(self.source_text)

        # Ligne du bas de la source : Tokens à gauche, Bouton à droite
        bottom_source_layout = QHBoxLayout()

        token_layout = QVBoxLayout()
        self.token_label = QLabel("Tokens : 0 / ?")
        self.token_label.setStyleSheet("color: palette(placeholder-text); font-size: 12px;")
        self.token_bar = QProgressBar()
        self.token_bar.setTextVisible(False)
        self.token_bar.setFixedHeight(6)
        self.token_bar.setFixedWidth(200)
        self.token_bar.setMinimumWidth(50)
        token_layout.addWidget(self.token_label)
        token_layout.addWidget(self.token_bar)

        bottom_source_layout.addLayout(token_layout)
        bottom_source_layout.addStretch()

        self.lbl_progress = QLabel("")
        self.lbl_progress.setStyleSheet("color: #4CAF50; font-weight: bold; font-size: 12px; margin-right: 15px;")
        bottom_source_layout.addWidget(self.lbl_progress)

        self.btn_generate = PrimaryButton(qta.icon("fa5s.magic", color="white"), " Générer les Cartes")
        self.btn_generate.clicked.connect(self.start_generation)
        bottom_source_layout.addWidget(self.btn_generate)

        self.btn_cancel = DangerButton(qta.icon("fa5s.stop", color="white"), " Annuler")
        self.btn_cancel.clicked.connect(self.cancel_generation)
        self.btn_cancel.hide()
        bottom_source_layout.addWidget(self.btn_cancel)

        source_layout.addLayout(bottom_source_layout)
        source_panel.setMinimumWidth(200)
        main_splitter.addWidget(source_panel)

        # ==========================================
        # BLOC 3 : RÉSULTATS (En Cartes scindées)
        # ==========================================
        bottom_splitter = QSplitter(Qt.Orientation.Horizontal)
        bottom_splitter.setHandleWidth(10)
        bottom_splitter.setChildrenCollapsible(False)

        # 3A. Panneau de gauche : Le Tableau
        table_panel = RoundedPanel()
        table_layout = QVBoxLayout(table_panel)
        table_layout.setContentsMargins(20, 20, 20, 20)

        lbl_title_3 = QLabel("RÉSULTATS (DOUBLE-CLIQUEZ POUR ÉDITER)")
        lbl_title_3.setStyleSheet("font-weight: bold; color: palette(placeholder-text); font-size: 11px; letter-spacing: 1px;")
        table_layout.addWidget(lbl_title_3)

        self.results_table = QTableWidget()
        self.results_table.horizontalHeader().setStretchLastSection(True)
        self.results_table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked)
        self.results_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.results_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.results_table.setAlternatingRowColors(True)
        self.results_table.itemChanged.connect(self.on_table_item_changed)
        self.results_table.itemSelectionChanged.connect(self.update_preview)
        # On retire la bordure native du tableau car le RoundedPanel s'en charge
        self.results_table.setFrameShape(QFrame.Shape.NoFrame)
        table_layout.addWidget(self.results_table)

        btn_save_layout = QHBoxLayout()
        btn_save_layout.addStretch()
        self.btn_save = PrimaryButton(qta.icon("fa5s.save", color="white"), " Sauvegarder dans la base")
        self.btn_save.clicked.connect(self.save_to_database)
        self.btn_save.setEnabled(False)
        btn_save_layout.addWidget(self.btn_save)
        table_layout.addLayout(btn_save_layout)

        # 3B. Panneau de droite : Aperçu & Logs
        right_panel = RoundedPanel()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(10, 10, 10, 10)  # Marges réduites pour laisser la place aux onglets

        right_tabs = QTabWidget()
        # Style pour intégrer parfaitement les onglets dans la carte
        right_tabs.setStyleSheet("""
            QTabWidget::pane { border: none; border-top: 1px solid palette(alternate-base); }
            QTabBar::tab { background: transparent; color: palette(text); padding: 8px 15px; margin-right: 2px; border-radius: 4px; }
            QTabBar::tab:selected { background: palette(alternate-base); font-weight: bold; }
            QTabBar::tab:hover:!selected { background: palette(window); }
        """)

        preview_container = QWidget()
        preview_layout = QVBoxLayout(preview_container)
        preview_layout.setContentsMargins(5, 15, 5, 5)

        controls_layout = QHBoxLayout()
        self.preview_card_selector = QComboBox()
        self.preview_card_selector.currentIndexChanged.connect(self.update_preview)

        self.preview_side_selector = QComboBox()
        self.preview_side_selector.addItems(["Voir Recto", "Voir Verso"])
        self.preview_side_selector.currentIndexChanged.connect(self.update_preview)

        controls_layout.addWidget(self.preview_card_selector)
        controls_layout.addWidget(self.preview_side_selector)
        preview_layout.addLayout(controls_layout)

        self.web_view = SafeWebEngineView()
        preview_layout.addWidget(self.web_view)

        right_tabs.addTab(preview_container, qta.icon("fa5s.eye"), " Aperçu")

        self.console_log = QTextEdit()
        self.console_log.setReadOnly(True)
        self.console_log.setFrameShape(QFrame.Shape.NoFrame)
        font = QFont("Consolas")
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.console_log.setFont(font)
        right_tabs.addTab(self.console_log, qta.icon("fa5s.terminal"), " Console IA")

        right_layout.addWidget(right_tabs)

        bottom_splitter.addWidget(table_panel)
        bottom_splitter.addWidget(right_panel)
        bottom_splitter.setSizes([500, 300])

        main_splitter.addWidget(bottom_splitter)
        main_splitter.setSizes([200, 500])

        layout.addWidget(main_splitter)

        self.refresh_selectors()
        self.load_documents()

        self.shortcut_generate = QShortcut(QKeySequence("Ctrl+Return"), self)
        self.shortcut_generate.activated.connect(self.start_generation)
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
            if current_llm:
                self.llm_selector.setCurrentIndex(self.llm_selector.findData(current_llm))
            self.llm_selector.blockSignals(False)

        # On remet les sélections
        if current_deck:
            self.deck_selector.setCurrentIndex(self.deck_selector.findData(current_deck))
        if current_model:
            self.model_selector.setCurrentIndex(self.model_selector.findData(current_model))
        if current_pipe:
            self.pipeline_selector.setCurrentIndex(self.pipeline_selector.findData(current_pipe))

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
            except (ValueError, AttributeError):
                pass

        self.token_bar.setMaximum(max_tokens)
        self.token_bar.setValue(min(estimated_tokens, max_tokens))
        self.token_label.setText(f"<b>Tokens : ~{estimated_tokens:,} / {max_tokens:,}</b>".replace(",", " "))

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

    @staticmethod
    def _parse_markdown_sections(text: str) -> list[tuple[str, str]]:
        sections = []
        current_title = ""
        current_content: list[str] = []

        for line in text.split("\n"):
            if line.startswith("#"):
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
            sections.append((current_title if current_title else "Texte", "\n".join(current_content)))

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
        llm_id = self.llm_selector.currentData()

        if not text.strip():
            show_toast(self, "Veuillez entrer du texte source.", is_error=True)
            return
        if not pipeline_id:
            show_toast(self, "Veuillez sélectionner un Pipeline IA.", is_error=True)
            return
        if not llm_id:
            show_toast(self, "Veuillez sélectionner un moteur IA.", is_error=True)
            return

        llm_config = LLMConfigModel.get_by_id(llm_id)
        p_name = llm_config.provider.lower()
        active_provider: LLMProvider
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
                api_key=os.environ.get("OPENAI_API_KEY", ""),
            )
        else:
            # Sécurité si un fournisseur (comme Anthropic brut) n'est pas encore implémenté
            active_provider = MockProvider()

        self.btn_generate.hide()
        self.btn_cancel.show()
        self.btn_cancel.setEnabled(True)

        self.btn_generate.setEnabled(False)
        self.results_table.setRowCount(0)
        self.web_view.clear_memory()
        self.console_log.clear()

        self.thread = GenerationThread(active_provider, text, model_id, pipeline_id)
        self.thread.progress.connect(self.update_progress)
        self.thread.log.connect(self.append_log)
        self.thread.finished.connect(self.on_generation_success)
        self.thread.error.connect(self.on_generation_error)
        self.thread.cancelled.connect(self.on_generation_cancelled)
        self.thread.start()

    @Slot()
    def cancel_generation(self) -> None:
        if self.thread is not None and self.thread.isRunning():
            self.thread.cancel()
            self.btn_cancel.setEnabled(False)
            self.btn_cancel.setText(" Arrêt en cours...")
            self.append_log("\n⏳ Demande d'arrêt de l'IA...")

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
        self.btn_generate.setText("✨ Regénérer les Cartes")
        self.btn_save.setEnabled(True)

        self.btn_cancel.hide()
        self.btn_generate.show()
        self.btn_generate.setEnabled(True)
        self.btn_generate.setText("Regénérer les Cartes")
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
        self.btn_generate.setText("✨ Générer les Cartes")
        QMessageBox.critical(self, "Erreur IA", error_msg)

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
            text_color = "#8C8C8C" if is_dark_mode() else "#6E6E6E"
            placeholder = f"""<div style='display: flex; height: 100vh; align-items: center; justify-content: center; color: {text_color}; font-family: sans-serif; text-align: center;'>Sélectionnez une ligne dans le tableau<br>pour prévisualiser la carte.</div>"""
            self.web_view.setHtmlSafe(placeholder)
            self.web_view.page().setBackgroundColor(Qt.GlobalColor.transparent)
            return

        row = selected_items[0].row()
        if row >= len(self.generated_notes):
            return

        current_data = self.generated_notes[row]
        model_id = self.model_selector.currentData()
        note_type = NoteTypeModel.get_by_id(model_id)
        if note_type is None:
            return

        templates = json.loads(note_type.templates) if note_type.templates else []
        is_cloze, selected_tmpl_idx = sync_preview_card_selector(
            selector=self.preview_card_selector,
            templates=templates,
            current_fields=current_data,
        )

        tmpl, card_idx = get_preview_template(
            templates=templates,
            is_cloze=is_cloze,
            selected_index=selected_tmpl_idx,
        )

        is_recto = self.preview_side_selector.currentIndex() == 0
        raw_html = tmpl.get("qfmt", "") if is_recto else tmpl.get("afmt", "")

        css = note_type.css_style if note_type.css_style else ""

        final_html = render_anki_card(
            raw_html=raw_html,
            css=css,
            fields_dict=current_data,
            is_recto=is_recto,
            front_html=tmpl.get("qfmt", ""),
            is_dark_mode=is_dark_mode(),
            template_index=card_idx,
        )

        media_dir = get_app_data_dir() / "media"
        media_dir.mkdir(exist_ok=True)
        base_url = QUrl.fromLocalFile(str(media_dir) + "/")

        self.web_view.setHtmlSafe(final_html, base_url)
        self.web_view.page().setBackgroundColor(Qt.GlobalColor.transparent)

    @Slot()
    def save_to_database(self) -> None:
        if not self.generated_notes:
            return

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
                        tags=json.dumps(["AnkiForge_AI"]),
                        status="new",
                    )
                    NoteVersionModel.create(
                        note=note,
                        version_number=1,
                        content=json.dumps(note_data, ensure_ascii=False),
                        source="ai",
                        is_active=True,
                    )
                    is_cloze = any("{{cloze:" in t.get("qfmt", "") or "{{cloze:" in t.get("afmt", "") for t in templates)

                    if is_cloze:
                        max_cloze = get_max_cloze_index(note_data)
                        num_cards = max(1, max_cloze)
                        for i in range(num_cards):
                            CardModel.create(note=note, deck=deck, template_index=i)
                    else:
                        for idx, _ in enumerate(templates):
                            CardModel.create(note=note, deck=deck, template_index=idx)

            show_toast(self, f"{len(self.generated_notes)} notes créées !")
            self.generated_notes.clear()
            self.results_table.setRowCount(0)
            self.web_view.clear_memory()
            self.btn_save.setEnabled(False)

        except Exception as e:
            QMessageBox.critical(self, "Erreur Base de donnée", f"Impossible de sauvegarder : {e}")

    @Slot()
    def on_generation_cancelled(self) -> None:
        self.btn_cancel.hide()
        self.btn_cancel.setText(" Annuler")
        self.btn_generate.show()
        self.btn_generate.setEnabled(True)
        self.btn_generate.setText(" Générer les Cartes")
        show_toast(self, "Génération annulée.", is_error=True)

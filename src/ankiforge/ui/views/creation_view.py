"""
Studio de Création - Split View Layout & Raccordement Métier d'origine (master).
- Alignement 100% sur la logique métier de la branche master :
  * NoteManager.create_note (génération atomique des cartes physiques Cloze/Basic)
  * AIProvider via ai_manager.create_provider_from_config
  * Prise en charge des signaux complets de CreationWorker (progress, log, finished, error, cancelled)
  * Dynamic Table Headers basés sur fields_schema du NoteTypeModel
  * Prévisualisation WebEngine + MathJax + Multi-appareils (CardPreviewWidget)
  * Toast notifications et messages système
"""

import json
import logging
from typing import Any, Optional

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QSplitter,
    QTableWidgetItem,
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
from ankiforge.services.workers.creation_worker import CreationTaskPayload, CreationWorker
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
from ankiforge.ui.widgets.card_preview_widget import CardPreviewWidget
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class CardEditDialog(QDialog):
    """Dialogue d'édition rapide d'une carte générée."""

    def __init__(self, front: str, back: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Éditer la carte")
        self.setMinimumWidth(500)
        self.setStyleSheet(f"background-color: {DesignTokens.BG_MAIN};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        lbl_front = QLabel("Recto :")
        lbl_front.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: bold;")
        self.edit_front = StyledTextEdit()
        self.edit_front.setPlainText(front)
        self.edit_front.setFixedHeight(100)

        lbl_back = QLabel("Verso :")
        lbl_back.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: bold;")
        self.edit_back = StyledTextEdit()
        self.edit_back.setPlainText(back)
        self.edit_back.setFixedHeight(120)

        layout.addWidget(lbl_front)
        layout.addWidget(self.edit_front)
        layout.addWidget(lbl_back)
        layout.addWidget(self.edit_back)

        btn_box = QHBoxLayout()
        btn_box.addStretch()

        btn_cancel = SecondaryButton("Annuler")
        btn_cancel.clicked.connect(self.reject)

        btn_save = PrimaryButton("Enregistrer")
        btn_save.clicked.connect(self.accept)

        btn_box.addWidget(btn_cancel)
        btn_box.addWidget(btn_save)

        layout.addLayout(btn_box)

    def get_data(self) -> tuple[str, str]:
        return self.edit_front.toPlainText().strip(), self.edit_back.toPlainText().strip()


class FlashcardPreview(QWidget):
    """Composant d'inspection et de validation des cartes générées."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("background-color: rgba(0, 0, 0, 0.1);")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Barre supérieure de navigation dans les résultats
        top_toolbar = QHBoxLayout()
        self.btn_prev = IconButton("ph.caret-left", "Carte précédente", 24)
        self.btn_next = IconButton("ph.caret-right", "Carte suivante", 24)
        self.lbl_counter = QLabel("0 / 0")
        self.lbl_counter.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-family: {DesignTokens.FONT_CODE}; font-weight: bold;")

        top_toolbar.addWidget(self.btn_prev)
        top_toolbar.addWidget(self.lbl_counter)
        top_toolbar.addWidget(self.btn_next)
        top_toolbar.addStretch()

        self.btn_toggle_verso = SecondaryButton("Masquer Verso")
        self.btn_toggle_verso.setIcon(load_phosphor_icon("ph.eye-slash", color=DesignTokens.TEXT_PRIMARY))
        top_toolbar.addWidget(self.btn_toggle_verso)

        layout.addLayout(top_toolbar)

        # Intégration de CardPreviewWidget (Moteur WebEngine + MathJax + multi-appareils)
        self.card_preview_widget = CardPreviewWidget(show_header=False)
        layout.addWidget(self.card_preview_widget, 1)

        # Barre d'actions en bas de carte
        bot_toolbar = QHBoxLayout()
        self.btn_valider = PrimaryButton("Valider")
        self.btn_valider.setIcon(load_phosphor_icon("ph.check", color="white"))

        self.btn_editer = SecondaryButton("Éditer")
        self.btn_editer.setIcon(load_phosphor_icon("ph.pencil-simple", color=DesignTokens.TEXT_PRIMARY))

        self.btn_rejeter = DangerButton("Rejeter", ghost=True)
        self.btn_rejeter.setIcon(load_phosphor_icon("ph.trash", color=DesignTokens.COLOR_RED))

        bot_toolbar.addWidget(self.btn_valider, 1)
        bot_toolbar.addWidget(self.btn_editer, 1)
        bot_toolbar.addWidget(self.btn_rejeter, 1)

        layout.addLayout(bot_toolbar)


class CreationView(QWidget):
    """
    Studio de Création AnkiForge — Intégration conforme à l'architecture master.
    """

    def __init__(self, ai_manager: Any = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.ai_manager = ai_manager
        self.generated_cards: list[dict[str, Any]] = []
        self.current_preview_index = 0
        self.verso_visible = True
        self.worker: Optional[CreationWorker] = None

        self._setup_ui()
        self._connect_signals()
        self.refresh_data()

    def _setup_ui(self) -> None:
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(self.main_splitter)

        # --- COL 1: Config IA Panel ---
        self.config_panel = IdePanel(detachable=True)
        self.config_panel.setMinimumWidth(240)

        config_content = QWidget()
        config_layout = QVBoxLayout(config_content)
        config_layout.setContentsMargins(12, 12, 12, 12)
        config_layout.setSpacing(14)

        def add_form_group(layout: QVBoxLayout, label_text: str, widget: QWidget) -> None:
            lbl = QLabel(label_text)
            lbl.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-weight: 600; font-size: 12px;")
            layout.addWidget(lbl)
            layout.addWidget(widget)

        self.pkg_input = StyledLineEdit()
        self.pkg_input.setPlaceholderText("Nom du paquet (ex: Science::Physique)")
        self.pkg_input.setText("Général")
        add_form_group(config_layout, "Paquet Cible :", self.pkg_input)

        self.model_combo = StyledComboBox()
        self.model_combo.currentIndexChanged.connect(self._on_model_changed)
        add_form_group(config_layout, "Modèle de Carte :", self.model_combo)

        self.engine_combo = StyledComboBox()
        add_form_group(config_layout, "Moteur IA :", self.engine_combo)

        self.pipeline_combo = StyledComboBox()
        add_form_group(config_layout, "Pipeline Agentique :", self.pipeline_combo)

        self.vision_cb = QCheckBox("Activer l'analyse Vision (Images/PDF)")
        self.vision_cb.setIcon(load_phosphor_icon("ph.eye", color="#eab308"))
        self.vision_cb.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; spacing: 8px;")
        config_layout.addWidget(self.vision_cb)

        config_layout.addStretch()

        moteur_content = QWidget()
        moteur_layout = QVBoxLayout(moteur_content)
        moteur_layout.setContentsMargins(12, 12, 12, 12)
        moteur_lbl = QLabel("Configuration avancée du LLM (Température, Top P, Max Tokens).")
        moteur_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 12px;")
        moteur_lbl.setWordWrap(True)
        moteur_layout.addWidget(moteur_lbl)
        moteur_layout.addStretch()

        self.config_panel.add_tab("Config IA", config_content, "ph.cpu", closable=False)
        self.config_panel.add_tab("Paramètres Moteur", moteur_content, "ph.gear", closable=False)

        self.main_splitter.addWidget(self.config_panel)

        # --- COL 2: Source + Results ---
        self.center_splitter = QSplitter(Qt.Orientation.Vertical)
        self.main_splitter.addWidget(self.center_splitter)

        # Panel Document Source
        self.source_panel = IdePanel(detachable=True)
        source_content = QWidget()
        source_layout = QVBoxLayout(source_content)
        source_layout.setContentsMargins(12, 12, 12, 12)
        source_layout.setSpacing(8)

        source_top_toolbar = QHBoxLayout()
        self.doc_selector = StyledComboBox()
        source_top_toolbar.addWidget(self.doc_selector, 1)

        self.btn_refresh = IconButton("ph.arrows-clockwise", tooltip="Actualiser la liste des documents", size=24)
        self.btn_refresh.clicked.connect(self.refresh_data)
        source_top_toolbar.addWidget(self.btn_refresh)

        source_layout.addLayout(source_top_toolbar)

        self.source_text_edit = StyledTextEdit()
        self.source_text_edit.setPlaceholderText("Saisissez ou collez votre texte source ici, ou sélectionnez un document ci-dessus...")
        source_layout.addWidget(self.source_text_edit, 1)

        source_bot_toolbar = QHBoxLayout()
        self.tokens_lbl = QLabel("Tokens estimés : 0")
        self.tokens_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-family: '{DesignTokens.FONT_CODE}'; font-size: 11px;")
        source_bot_toolbar.addWidget(self.tokens_lbl)
        source_bot_toolbar.addStretch()

        self.btn_generate = PrimaryButton("Générer les Cartes")
        self.btn_generate.setIcon(load_phosphor_icon("ph.magic-wand", color="white"))

        self.btn_cancel = DangerButton("Arrêter", ghost=True)
        self.btn_cancel.setIcon(load_phosphor_icon("ph.stop-circle", color=DesignTokens.COLOR_RED))
        self.btn_cancel.hide()

        source_bot_toolbar.addWidget(self.btn_generate)
        source_bot_toolbar.addWidget(self.btn_cancel)
        source_layout.addLayout(source_bot_toolbar)

        self.source_panel.add_tab("Document Source", source_content, "ph.text-align-left", closable=False)
        self.center_splitter.addWidget(self.source_panel)

        # Panel Cartes Générées
        self.results_panel = IdePanel(detachable=True)

        cartes_content = QWidget()
        cartes_layout = QVBoxLayout(cartes_content)
        cartes_layout.setContentsMargins(0, 0, 0, 0)

        self.results_splitter = QSplitter(Qt.Orientation.Horizontal)

        # Gauche : Table des résultats
        table_container = QWidget()
        table_layout = QVBoxLayout(table_container)
        table_layout.setContentsMargins(12, 12, 12, 12)
        table_layout.setSpacing(8)
        table_container.setStyleSheet(f"border-right: 1px solid {DesignTokens.BORDER_COLOR};")

        self.results_table = StyledTableWidget(["Recto", "Verso", "Statut"])
        self.results_table.setSelectionBehavior(StyledTableWidget.SelectionBehavior.SelectRows)
        self.results_table.itemSelectionChanged.connect(self._on_table_selection_changed)
        self.results_table.itemChanged.connect(self._on_cell_edited)
        table_layout.addWidget(self.results_table, 1)

        table_bot_toolbar = QHBoxLayout()
        table_bot_toolbar.addStretch()
        self.btn_save_anki = PrimaryButton("Sauvegarder dans Anki")
        self.btn_save_anki.setIcon(load_phosphor_icon("ph.floppy-disk", color="white"))
        table_bot_toolbar.addWidget(self.btn_save_anki)
        table_layout.addLayout(table_bot_toolbar)

        self.results_splitter.addWidget(table_container)

        # Droite : Aperçu interactif WebEngine
        self.preview_widget = FlashcardPreview()
        self.results_splitter.addWidget(self.preview_widget)

        cartes_layout.addWidget(self.results_splitter)

        erreurs_content = QWidget()
        erreurs_layout = QVBoxLayout(erreurs_content)
        erreurs_layout.setContentsMargins(12, 12, 12, 12)
        self.err_lbl = QLabel("Aucune erreur lors du processus de génération.")
        self.err_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 12px;")
        erreurs_layout.addWidget(self.err_lbl)
        erreurs_layout.addStretch()

        self.results_panel.add_tab("Cartes Générées", cartes_content, "ph.list-numbers", closable=False)
        self.results_panel.add_tab("Journal des Erreurs", erreurs_content, "ph.warning-circle", closable=False)

        self.center_splitter.addWidget(self.results_panel)
        self.center_splitter.setSizes([320, 480])
        self.main_splitter.setSizes([260, 800])

    def _connect_signals(self) -> None:
        self.source_text_edit.textChanged.connect(self._on_text_changed)
        self.doc_selector.currentIndexChanged.connect(self._on_document_selected)

        self.btn_generate.clicked.connect(self._on_generate)
        self.btn_cancel.clicked.connect(self._on_cancel_generation)
        self.btn_save_anki.clicked.connect(self._on_save_anki)

        self.preview_widget.btn_prev.clicked.connect(self._on_prev_card)
        self.preview_widget.btn_next.clicked.connect(self._on_next_card)
        self.preview_widget.btn_toggle_verso.clicked.connect(self._on_toggle_verso)
        self.preview_widget.btn_valider.clicked.connect(self._on_validate_card)
        self.preview_widget.btn_editer.clicked.connect(self._on_edit_card)
        self.preview_widget.btn_rejeter.clicked.connect(self._on_reject_card)

    def refresh_data(self) -> None:
        """Recharge les données dynamiques depuis la base Peewee (Decks, NoteTypes, Engines, Pipelines, Docs)."""
        try:
            # Note Types
            self.model_combo.blockSignals(True)
            self.model_combo.clear()
            note_types = list(NoteTypeModel.select())
            if note_types:
                for nt in note_types:
                    self.model_combo.addItem(nt.name, userData=nt)
            else:
                self.model_combo.addItem("Basique (Recto/Verso)")
                self.model_combo.addItem("Texte à trous (Cloze)")
            self.model_combo.blockSignals(False)

            # Engines LLM
            self.engine_combo.blockSignals(True)
            self.engine_combo.clear()
            engines = list(LLMConfigModel.select())
            if engines:
                for eg in engines:
                    self.engine_combo.addItem(eg.name, userData=eg)
            else:
                self.engine_combo.addItem("Claude 3.5 Sonnet")
                self.engine_combo.addItem("GPT-4o")
            self.engine_combo.blockSignals(False)

            # Pipelines
            self.pipeline_combo.blockSignals(True)
            self.pipeline_combo.clear()
            pipelines = list(PipelineModel.select())
            if pipelines:
                for pipe in pipelines:
                    self.pipeline_combo.addItem(pipe.name, userData=pipe)
            else:
                self.pipeline_combo.addItem("Standard (Excellence)")
                self.pipeline_combo.addItem("Rapide (Fast)")
            self.pipeline_combo.blockSignals(False)

            # Documents
            self.doc_selector.blockSignals(True)
            self.doc_selector.clear()
            self.doc_selector.addItem("-- Sélectionner un document existant --", userData=None)
            docs = list(DocumentModel.select())
            for doc in docs:
                self.doc_selector.addItem(f"📄 {doc.title}", userData=doc)
            self.doc_selector.blockSignals(False)

            # Decks suggestions
            decks = list(DeckModel.select())
            if decks:
                self.pkg_input.setText(decks[0].name)

            self._on_model_changed()

        except Exception as e:
            logger.warning("Erreur lors de la mise à jour des combos creation_view: %s", e)

    def is_dirty(self) -> bool:
        return len(self.generated_cards) > 0

    @Slot()
    def _on_model_changed(self) -> None:
        selected_nt = self.model_combo.currentData()
        fields = ["Recto", "Verso", "Statut"]
        if selected_nt and isinstance(selected_nt, NoteTypeModel) and selected_nt.fields_schema:
            try:
                schema_fields = json.loads(selected_nt.fields_schema)
                if isinstance(schema_fields, list) and schema_fields:
                    fields = schema_fields + ["Statut"]
            except Exception:
                pass  # nosec B110

        self.results_table.blockSignals(True)
        self.results_table.clear()
        self.results_table.setColumnCount(len(fields))
        self.results_table.setHorizontalHeaderLabels(fields)
        self.results_table.setRowCount(0)
        self.results_table.blockSignals(False)

    @Slot()
    def _on_text_changed(self) -> None:
        text = self.source_text_edit.toPlainText()
        words = len(text.split())
        estimated_tokens = int(words * 1.3)
        self.tokens_lbl.setText(f"Tokens estimés : ~{estimated_tokens} ({words} mots)")

    @Slot(int)
    def _on_document_selected(self, index: int) -> None:
        doc: Optional[DocumentModel] = self.doc_selector.currentData()
        if doc and hasattr(doc, "content") and doc.content:
            self.source_text_edit.setPlainText(doc.content)

    @Slot()
    def _on_generate(self) -> None:
        text_source = self.source_text_edit.toPlainText().strip()
        if not text_source:
            show_toast(self, "Veuillez saisir un texte source ou sélectionner un document.", is_error=True)
            return

        selected_nt = self.model_combo.currentData()
        selected_pipeline = self.pipeline_combo.currentData()
        selected_engine = self.engine_combo.currentData()

        note_type_id = selected_nt.id if selected_nt and hasattr(selected_nt, "id") else 1
        note_type_fields = selected_nt.fields_schema if selected_nt and hasattr(selected_nt, "fields_schema") else '["Front", "Back"]'

        pipeline_id = selected_pipeline.id if selected_pipeline and hasattr(selected_pipeline, "id") else 1
        pipeline_name = selected_pipeline.name if selected_pipeline and hasattr(selected_pipeline, "name") else "Standard"

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
                    "name": "Generator",
                    "system_prompt": 'Tu es un expert Anki. Génère des cartes flash sous forme de JSON array [{"front": "...", "back": "..."}].',
                    "output_format": "json",
                }
            ]

        payload = CreationTaskPayload(
            text_source=text_source,
            note_type_id=note_type_id,
            note_type_fields_schema=note_type_fields,
            pipeline_id=pipeline_id,
            pipeline_name=pipeline_name,
            pipeline_steps=pipeline_steps,
            use_vision=self.vision_cb.isChecked(),
        )

        ai_provider = None
        if self.ai_manager:
            if selected_engine and isinstance(selected_engine, LLMConfigModel) and hasattr(self.ai_manager, "create_provider_from_config"):
                try:
                    ai_provider = self.ai_manager.create_provider_from_config(selected_engine)
                except Exception:
                    pass  # nosec B110
            if not ai_provider and hasattr(self.ai_manager, "get_active_provider"):
                try:
                    ai_provider = self.ai_manager.get_active_provider()
                except Exception:
                    pass  # nosec B110

        self.btn_generate.hide()
        self.btn_cancel.show()
        self.btn_cancel.setEnabled(True)

        self.worker = CreationWorker(ai_provider=ai_provider, payload=payload)
        self.worker.progress.connect(self._on_generation_progress)
        self.worker.log.connect(self._on_generation_log)
        self.worker.finished.connect(self._on_generation_finished)
        self.worker.error.connect(self._on_generation_error)
        self.worker.cancelled.connect(self._on_generation_cancelled)
        self.worker.start()

    @Slot()
    def _on_cancel_generation(self) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.btn_cancel.setEnabled(False)
            self.btn_cancel.setText("Arrêt...")

    @Slot(str)
    def _on_generation_progress(self, msg: str) -> None:
        self.btn_cancel.setText(f"Arrêter ({msg})")

    @Slot(str)
    def _on_generation_log(self, text: str) -> None:
        logger.info("[CreationView Log] %s", text)

    @Slot(list)
    def _on_generation_finished(self, results: list) -> None:
        self.btn_cancel.hide()
        self.btn_generate.show()
        self.btn_generate.setEnabled(True)

        self.generated_cards = results
        self.current_preview_index = 0
        self._update_table()
        self._update_preview()
        show_toast(self, f"Génération terminée : {len(results)} cartes créées !")

    @Slot(str)
    def _on_generation_error(self, error: str) -> None:
        self.btn_cancel.hide()
        self.btn_generate.show()
        self.btn_generate.setEnabled(True)

        self.err_lbl.setText(f"Erreur de génération : {error}")
        QMessageBox.critical(self, "Erreur de génération", f"Le moteur IA a rencontré une erreur :\n{error}")

    @Slot()
    def _on_generation_cancelled(self) -> None:
        self.btn_cancel.hide()
        self.btn_cancel.setText("Arrêter")
        self.btn_generate.show()
        self.btn_generate.setEnabled(True)
        show_toast(self, "Génération annulée.", is_error=True)

    def _update_table(self) -> None:
        self.results_table.blockSignals(True)
        self.results_table.setRowCount(len(self.generated_cards))

        col_count = self.results_table.columnCount()
        status_col = col_count - 1

        for i, card in enumerate(self.generated_cards):
            status = card.get("status", "PRÊT")

            for col in range(status_col):
                header_item = self.results_table.horizontalHeaderItem(col)
                h_name = header_item.text() if header_item else f"Field_{col+1}"
                val = card.get(h_name, card.get(h_name.lower(), card.get("front" if col == 0 else "back", "")))
                if isinstance(val, list):
                    val = "<br>".join([str(item) for item in val])
                elif not isinstance(val, str):
                    val = str(val) if val is not None else ""

                self.results_table.setItem(i, col, QTableWidgetItem(val))

            badge_widget = QWidget()
            badge_layout = QHBoxLayout(badge_widget)
            badge_layout.setContentsMargins(4, 0, 4, 0)
            badge_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

            color = DesignTokens.COLOR_GREEN
            if status == "REJETÉ":
                color = DesignTokens.COLOR_RED
            elif status == "ÉDITÉ":
                color = DesignTokens.COLOR_PURPLE

            badge = Badge(status, variant="outline", color=color)
            badge_layout.addWidget(badge)
            self.results_table.setCellWidget(i, status_col, badge_widget)

        self.results_table.blockSignals(False)

    @Slot()
    def _on_table_selection_changed(self) -> None:
        selected = self.results_table.selectedItems()
        if selected:
            row = selected[0].row()
            if 0 <= row < len(self.generated_cards):
                self.current_preview_index = row
                self._update_preview()

    @Slot(QTableWidgetItem)
    def _on_cell_edited(self, item: QTableWidgetItem) -> None:
        row = item.row()
        col = item.column()
        col_count = self.results_table.columnCount()
        if 0 <= row < len(self.generated_cards) and col < col_count - 1:
            header_item = self.results_table.horizontalHeaderItem(col)
            h_name = header_item.text() if header_item else ("front" if col == 0 else "back")
            self.generated_cards[row][h_name] = item.text()
            if col == 0:
                self.generated_cards[row]["front"] = item.text()
            elif col == 1:
                self.generated_cards[row]["back"] = item.text()

            self.generated_cards[row]["status"] = "ÉDITÉ"
            self._update_preview()

    def _update_preview(self) -> None:
        if not self.generated_cards:
            self.preview_widget.card_preview_widget.set_empty_state("Aucune carte générée.")
            self.preview_widget.lbl_counter.setText("0 / 0")
            return

        total = len(self.generated_cards)
        self.current_preview_index = max(0, min(self.current_preview_index, total - 1))
        self.preview_widget.lbl_counter.setText(f"{self.current_preview_index + 1} / {total}")

        card = self.generated_cards[self.current_preview_index]
        recto = card.get("front", card.get("Front", ""))
        verso = card.get("back", card.get("Back", ""))

        selected_nt = self.model_combo.currentData()
        note_type = selected_nt if isinstance(selected_nt, NoteTypeModel) else None

        fields_dict: dict[str, str] = {
            "Front": recto,
            "Back": verso,
            "front": recto,
            "back": verso,
            "Question": recto,
            "Answer": verso,
        }

        # Include custom dynamic fields
        for k, v in card.items():
            fields_dict[str(k)] = str(v)

        if not self.verso_visible:
            fields_dict["Back"] = ""
            fields_dict["back"] = ""
            fields_dict["Answer"] = ""

        override_templates = None
        if not note_type or not getattr(note_type, "templates", None):
            override_templates = [{"name": "Carte 1", "qfmt": "{{Front}}", "afmt": "{{FrontSide}}<hr id=answer>{{Back}}"}]

        self.preview_widget.card_preview_widget.update_preview(
            note_type=note_type,
            fields_dict=fields_dict,
            override_templates=override_templates,
        )

    @Slot()
    def _on_save_anki(self) -> None:
        if not self.generated_cards:
            show_toast(self, "Aucune carte générée à sauvegarder.", is_error=True)
            return

        try:
            deck_name = self.pkg_input.text().strip() or "Général"
            deck, _ = DeckModel.get_or_create(name=deck_name)

            selected_nt = self.model_combo.currentData()
            note_type = selected_nt if isinstance(selected_nt, NoteTypeModel) else NoteTypeModel.select().first()
            if not note_type:
                note_type = NoteTypeModel.create(name="Basic", fields_schema='["Front", "Back"]', templates="[]", css_style="")

            saved_count = 0
            for card in self.generated_cards:
                if card.get("status") == "REJETÉ":
                    continue

                # Use NoteManager to create note + Cloze/Basic cards atomically
                NoteManager.create_note(
                    note_type=note_type,
                    deck=deck,
                    content_dict=card,
                    tags=["AnkiForge_AI"],
                    status="new",
                    source="ai",
                )
                saved_count += 1

            show_toast(self, f"{saved_count} cartes sauvegardées avec succès dans '{deck_name}' !")
            QMessageBox.information(self, "Sauvegarde Anki", f"{saved_count} cartes ont été créées dans le paquet '{deck_name}'.")

            self.generated_cards.clear()
            self.results_table.setRowCount(0)
            self.preview_widget.card_preview_widget.clear_memory()

        except Exception as e:
            logger.exception("Erreur lors de la sauvegarde dans la base : %s", e)
            QMessageBox.critical(self, "Erreur", f"Erreur lors de la sauvegarde : {str(e)}")

    @Slot()
    def _on_prev_card(self) -> None:
        if self.current_preview_index > 0:
            self.current_preview_index -= 1
            self.results_table.selectRow(self.current_preview_index)
            self._update_preview()

    @Slot()
    def _on_next_card(self) -> None:
        if self.current_preview_index < len(self.generated_cards) - 1:
            self.current_preview_index += 1
            self.results_table.selectRow(self.current_preview_index)
            self._update_preview()

    @Slot()
    def _on_toggle_verso(self) -> None:
        self.verso_visible = not self.verso_visible
        icon_name = "ph.eye" if not self.verso_visible else "ph.eye-slash"
        btn_text = "Voir Verso" if not self.verso_visible else "Masquer Verso"
        self.preview_widget.btn_toggle_verso.setText(btn_text)
        self.preview_widget.btn_toggle_verso.setIcon(load_phosphor_icon(icon_name, color=DesignTokens.TEXT_PRIMARY))
        self._update_preview()

    @Slot()
    def _on_validate_card(self) -> None:
        if self.generated_cards and 0 <= self.current_preview_index < len(self.generated_cards):
            self.generated_cards[self.current_preview_index]["status"] = "VALIDÉ"
            self._update_table()

    @Slot()
    def _on_edit_card(self) -> None:
        if not self.generated_cards or not (0 <= self.current_preview_index < len(self.generated_cards)):
            return

        card = self.generated_cards[self.current_preview_index]
        dialog = CardEditDialog(card.get("front", ""), card.get("back", ""), parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_front, new_back = dialog.get_data()
            self.generated_cards[self.current_preview_index]["front"] = new_front
            self.generated_cards[self.current_preview_index]["back"] = new_back
            self.generated_cards[self.current_preview_index]["status"] = "ÉDITÉ"
            self._update_table()
            self._update_preview()

    @Slot()
    def _on_reject_card(self) -> None:
        if self.generated_cards and 0 <= self.current_preview_index < len(self.generated_cards):
            self.generated_cards[self.current_preview_index]["status"] = "REJETÉ"
            self._update_table()

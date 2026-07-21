from typing import Any

from ankiforge.utils.icon_loader import load_phosphor_icon
from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QSplitter, QLabel, QFrame, QCheckBox, QTableWidgetItem, QMessageBox
from PySide6.QtCore import Qt, QThread, Signal, Slot
import uuid

from ankiforge.database.models import NoteTypeModel, DeckModel, LLMConfigModel, NoteModel, CardModel

from ankiforge.ui.theme import DesignTokens, apply_shadow
from ankiforge.ui.components import IdePanel, PrimaryButton, SecondaryButton, DangerButton, StyledTextEdit, StyledTableWidget, StyledComboBox, IconButton, Badge, StyledLineEdit


class CreationWorker(QThread):
    generation_finished = Signal(list)
    generation_error = Signal(str)

    def __init__(self, ai_manager, text, deck_name, note_type, engine, pipeline):
        super().__init__()
        self.ai_manager = ai_manager
        self.text = text
        self.deck_name = deck_name
        self.note_type = note_type
        self.engine = engine
        self.pipeline = pipeline

    def run(self):
        try:
            import time

            time.sleep(1)
            results = [
                {"front": f"Concept important dans {self.deck_name} ?", "back": "Une explication détaillée.", "status": "PRÊT"},
                {"front": "Quelle est la caractéristique principale ?", "back": "C'est très performant.", "status": "PRÊT"},
            ]
            self.generation_finished.emit(results)
        except Exception as e:
            self.generation_error.emit(str(e))


class FlashcardPreview(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("""
            FlashcardPreview {
                background-color: rgba(0, 0, 0, 0.1);
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        top_toolbar = QHBoxLayout()
        self.btn_prev = IconButton("ph.caret-left", "Précédent", 24)
        self.btn_next = IconButton("ph.caret-right", "Suivant", 24)
        self.lbl_counter = QLabel("1 / 2")
        self.lbl_counter.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-family: {DesignTokens.FONT_CODE};")

        top_toolbar.addWidget(self.btn_prev)
        top_toolbar.addWidget(self.lbl_counter)
        top_toolbar.addWidget(self.btn_next)
        top_toolbar.addStretch()

        self.btn_toggle_verso = SecondaryButton("Masquer Verso")
        self.btn_toggle_verso.setIcon(load_phosphor_icon("ph.eye-slash", color=DesignTokens.TEXT_PRIMARY))
        top_toolbar.addWidget(self.btn_toggle_verso)

        layout.addLayout(top_toolbar)

        self.card_frame = QFrame()
        self.card_frame.setStyleSheet(f"""
            QFrame {{
                background-color: #1a1d24;
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-top: 4px solid qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6366f1, stop:1 #8b5cf6);
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)
        apply_shadow(self.card_frame, blur=8, offset_y=4)

        card_layout = QVBoxLayout(self.card_frame)
        card_layout.setContentsMargins(24, 24, 24, 24)
        card_layout.setSpacing(16)

        self.lbl_front = QLabel("La capitale de la France ?")
        self.lbl_front.setStyleSheet(f"font-size: 16px; color: {DesignTokens.TEXT_PRIMARY}; border: none;")
        self.lbl_front.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_front.setWordWrap(True)
        card_layout.addWidget(self.lbl_front)

        self.divider = QFrame()
        self.divider.setFrameShape(QFrame.Shape.HLine)
        self.divider.setStyleSheet(f"color: {DesignTokens.BORDER_COLOR}; border: none; border-bottom: 1px solid {DesignTokens.BORDER_COLOR};")

        div_layout = QVBoxLayout()
        div_layout.addWidget(self.divider)
        div_lbl = QLabel("VERSO")
        div_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; text-transform: uppercase; border: none;")
        div_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        div_layout.addWidget(div_lbl)

        card_layout.addLayout(div_layout)

        self.lbl_back = QLabel("Paris")
        self.lbl_back.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {DesignTokens.ACCENT_PRIMARY}; border: none;")
        self.lbl_back.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_back.setWordWrap(True)
        card_layout.addWidget(self.lbl_back)

        card_layout.addStretch()

        layout.addWidget(self.card_frame, 1)

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
    Studio de Création - Split View Layout
    """

    def __init__(self, ai_manager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ai_manager = ai_manager
        self.generated_cards: list[dict[str, Any]] = []
        self.current_preview_index = 0
        self.verso_visible = True
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(16)

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(self.main_splitter)

        # --- COL 1: Config IA Panel ---
        self.config_panel = IdePanel(detachable=True)
        self.config_panel.setMinimumWidth(200)

        config_content = QWidget()
        config_layout = QVBoxLayout(config_content)
        config_layout.setContentsMargins(16, 16, 16, 16)
        config_layout.setSpacing(16)

        def add_form_group(layout, label_text, widget):
            lbl = QLabel(label_text)
            lbl.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-weight: 500;")
            layout.addWidget(lbl)
            layout.addWidget(widget)
            layout.addSpacing(4)

        self.pkg_input = StyledLineEdit()
        self.pkg_input.setPlaceholderText("Nom du paquet")
        add_form_group(config_layout, "Paquet :", self.pkg_input)

        self.model_combo = StyledComboBox()
        self.model_combo.addItems(["Basique (Recto/Verso)", "Texte à trous"])
        add_form_group(config_layout, "Modèle :", self.model_combo)

        self.engine_combo = StyledComboBox()
        self.engine_combo.addItems(["Claude 3.5 Sonnet", "GPT-4o"])
        add_form_group(config_layout, "Moteur :", self.engine_combo)

        self.pipeline_combo = StyledComboBox()
        self.pipeline_combo.addItems(["Excellence (Standard)", "Rapide (Fast)"])
        add_form_group(config_layout, "Pipeline :", self.pipeline_combo)

        self.vision_cb = QCheckBox("Activer Vision (PDF/Images)")
        self.vision_cb.setIcon(load_phosphor_icon("ph.eye", color="#eab308"))
        self.vision_cb.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; spacing: 8px;")
        config_layout.addWidget(self.vision_cb)

        config_layout.addStretch()

        moteur_content = QWidget()
        moteur_layout = QVBoxLayout(moteur_content)
        moteur_layout.setContentsMargins(16, 16, 16, 16)
        moteur_lbl = QLabel("Paramètres avancés du moteur (Température, Top P, etc.) à venir...")
        moteur_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED};")
        moteur_lbl.setWordWrap(True)
        moteur_layout.addWidget(moteur_lbl)
        moteur_layout.addStretch()

        self.config_panel.add_tab("Config IA", config_content, "ph.cpu", closable=True)
        self.config_panel.add_tab("Moteur", moteur_content, "ph.gear", closable=True)

        self.main_splitter.addWidget(self.config_panel)

        # --- COL 2: Source + Results ---
        self.center_splitter = QSplitter(Qt.Orientation.Vertical)
        self.main_splitter.addWidget(self.center_splitter)

        # Source Panel
        self.source_panel = IdePanel(detachable=True)
        source_content = QWidget()
        source_layout = QVBoxLayout(source_content)
        source_layout.setContentsMargins(16, 16, 16, 16)
        source_layout.setSpacing(8)

        source_top_toolbar = QHBoxLayout()
        self.doc_selector = StyledComboBox()
        source_top_toolbar.addWidget(self.doc_selector, 1)
        self.btn_refresh = IconButton("ph.arrows-clockwise", "Actualiser", 32)
        source_top_toolbar.addWidget(self.btn_refresh)
        source_layout.addLayout(source_top_toolbar)

        self.source_text_edit = StyledTextEdit()
        self.source_text_edit.setPlaceholderText("Collez votre texte source ici ou sélectionnez un document...")
        source_layout.addWidget(self.source_text_edit, 1)

        source_bot_toolbar = QHBoxLayout()
        self.tokens_lbl = QLabel("Tokens estimés : 0")
        self.tokens_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-family: '{DesignTokens.FONT_CODE}'; font-size: 11px;")
        source_bot_toolbar.addWidget(self.tokens_lbl)
        source_bot_toolbar.addStretch()

        self.btn_generate = PrimaryButton("Générer les Cartes")
        self.btn_generate.setIcon(load_phosphor_icon("ph.magic-wand", color="white"))
        source_bot_toolbar.addWidget(self.btn_generate)
        source_layout.addLayout(source_bot_toolbar)

        self.source_panel.add_tab("Document Source", source_content, "ph.text-align-left", closable=True)
        self.center_splitter.addWidget(self.source_panel)

        # Results Panel
        self.results_panel = IdePanel(detachable=True)

        # View toggles in header
        self.btn_view_list = IconButton("ph.list-dashes", "List mode", 24)
        self.btn_view_split = IconButton("ph.columns", "Split mode", 24)
        self.btn_view_split.setStyleSheet(f"background-color: {DesignTokens.BG_HOVER}; border-radius: {DesignTokens.RADIUS_SM}px;")
        self.btn_view_preview = IconButton("ph.monitor", "Preview mode", 24)

        self.results_panel.add_header_widget(self.btn_view_list)
        self.results_panel.add_header_widget(self.btn_view_split)
        self.results_panel.add_header_widget(self.btn_view_preview)
        self.results_panel.add_header_separator()

        cartes_content = QWidget()
        cartes_layout = QVBoxLayout(cartes_content)
        cartes_layout.setContentsMargins(0, 0, 0, 0)

        self.results_splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: Table
        table_container = QWidget()
        table_layout = QVBoxLayout(table_container)
        table_layout.setContentsMargins(16, 16, 16, 16)
        table_container.setStyleSheet(f"border-right: 1px solid {DesignTokens.BORDER_COLOR};")

        self.results_table = StyledTableWidget(["Recto", "Verso", "Statut"])
        table_layout.addWidget(self.results_table, 1)

        table_bot_toolbar = QHBoxLayout()
        table_bot_toolbar.addStretch()
        self.btn_save_anki = PrimaryButton("Sauvegarder dans Anki")
        self.btn_save_anki.setIcon(load_phosphor_icon("ph.floppy-disk", color="white"))
        table_bot_toolbar.addWidget(self.btn_save_anki)
        table_layout.addLayout(table_bot_toolbar)

        self.results_splitter.addWidget(table_container)

        # Right: Preview
        self.preview_widget = FlashcardPreview()
        self.results_splitter.addWidget(self.preview_widget)

        cartes_layout.addWidget(self.results_splitter)

        erreurs_content = QWidget()
        erreurs_layout = QVBoxLayout(erreurs_content)
        erreurs_layout.setContentsMargins(16, 16, 16, 16)
        err_lbl = QLabel("Aucune erreur lors de la génération.")
        err_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED};")
        erreurs_layout.addWidget(err_lbl)
        erreurs_layout.addStretch()

        self.results_panel.add_tab("Cartes Générées (2)", cartes_content, "ph.list-numbers", closable=True)
        self.results_panel.add_tab("Erreurs", erreurs_content, "ph.warning-circle", closable=True)

        self.center_splitter.addWidget(self.results_panel)
        self.center_splitter.setSizes([300, 500])
        self.main_splitter.setSizes([280, 800])

        self.main_splitter.setCollapsible(0, True)
        self.main_splitter.setCollapsible(1, True)
        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 1)

        self.center_splitter.setCollapsible(0, True)
        self.center_splitter.setCollapsible(1, True)
        self.center_splitter.setStretchFactor(0, 1)
        self.center_splitter.setStretchFactor(1, 1)

        self.results_splitter.setCollapsible(0, True)
        self.results_splitter.setCollapsible(1, True)
        self.results_splitter.setStretchFactor(0, 3)
        self.results_splitter.setStretchFactor(1, 2)

    def _connect_signals(self) -> None:
        self.btn_generate.clicked.connect(self._on_generate)
        self.btn_save_anki.clicked.connect(self._on_save_anki)

        self.preview_widget.btn_prev.clicked.connect(self._on_prev_card)
        self.preview_widget.btn_next.clicked.connect(self._on_next_card)
        self.preview_widget.btn_toggle_verso.clicked.connect(self._on_toggle_verso)
        self.preview_widget.btn_valider.clicked.connect(self._on_validate_card)
        self.preview_widget.btn_editer.clicked.connect(self._on_edit_card)
        self.preview_widget.btn_rejeter.clicked.connect(self._on_reject_card)

    def refresh_data(self) -> None:
        try:
            self.model_combo.clear()
            note_types = NoteTypeModel.select()
            if note_types.count() > 0:
                self.model_combo.addItems([nt.name for nt in note_types])
            else:
                self.model_combo.addItems(["Basique (Recto/Verso)", "Texte à trous"])

            self.engine_combo.clear()
            engines = LLMConfigModel.select()
            if engines.count() > 0:
                self.engine_combo.addItems([e.name for e in engines])
            else:
                self.engine_combo.addItems(["Claude 3.5 Sonnet", "GPT-4o"])
        except Exception:
            pass  # nosec B110

    def is_dirty(self) -> bool:
        return len(self.generated_cards) > 0

    @Slot()
    def _on_generate(self) -> None:
        self.btn_generate.setEnabled(False)
        self.worker = CreationWorker(
            self.ai_manager, self.source_text_edit.toPlainText(), self.pkg_input.text(), self.model_combo.currentText(), self.engine_combo.currentText(), self.pipeline_combo.currentText()
        )
        self.worker.generation_finished.connect(self._on_generation_finished)
        self.worker.generation_error.connect(self._on_generation_error)
        self.worker.start()

    @Slot(list)
    def _on_generation_finished(self, results: list) -> None:
        self.btn_generate.setEnabled(True)
        self.generated_cards = results
        self.current_preview_index = 0
        self._update_table()
        self._update_preview()

    @Slot(str)
    def _on_generation_error(self, error: str) -> None:
        self.btn_generate.setEnabled(True)
        QMessageBox.critical(self, "Erreur", f"Échec de la génération : {error}")

    def _update_table(self) -> None:
        self.results_table.setRowCount(len(self.generated_cards))
        for i, card in enumerate(self.generated_cards):
            self.results_table.setItem(i, 0, QTableWidgetItem(card["front"]))
            self.results_table.setItem(i, 1, QTableWidgetItem(card["back"]))

            badge_widget = QWidget()
            badge_layout = QHBoxLayout(badge_widget)
            badge_layout.setContentsMargins(4, 0, 4, 0)
            badge_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            badge = Badge(card["status"], variant="outline", color=DesignTokens.COLOR_GREEN)
            badge_layout.addWidget(badge)
            self.results_table.setCellWidget(i, 2, badge_widget)

    def _update_preview(self) -> None:
        if not self.generated_cards:
            self.preview_widget.lbl_front.setText("Aucune carte")
            self.preview_widget.lbl_back.setText("")
            self.preview_widget.lbl_counter.setText("0 / 0")
            return

        total = len(self.generated_cards)
        self.preview_widget.lbl_counter.setText(f"{self.current_preview_index + 1} / {total}")

        card = self.generated_cards[self.current_preview_index]
        self.preview_widget.lbl_front.setText(card["front"])
        self.preview_widget.lbl_back.setText(card["back"])

        self.preview_widget.lbl_back.setVisible(self.verso_visible)
        self.preview_widget.divider.setVisible(self.verso_visible)

    @Slot()
    def _on_save_anki(self) -> None:
        if not self.generated_cards:
            return

        try:
            deck, _ = DeckModel.get_or_create(name=self.pkg_input.text() or "Default")
            note_type = NoteTypeModel.select().first()
            if not note_type:
                note_type = NoteTypeModel.create(name="Basic", fields_schema='["Front", "Back"]', templates="[]", css_style="")

            for card in self.generated_cards:
                note = NoteModel.create(guid=str(uuid.uuid4()), note_type=note_type, tags="IA_Generated")
                CardModel.create(note=note, deck=deck)
                note.add_version({"front": card["front"], "back": card["back"]}, source="ai")

            QMessageBox.information(self, "Sauvegarde", f"{len(self.generated_cards)} cartes sauvegardées avec succès.")
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Erreur lors de la sauvegarde: {str(e)}")

    @Slot()
    def _on_prev_card(self) -> None:
        if self.current_preview_index > 0:
            self.current_preview_index -= 1
            self._update_preview()

    @Slot()
    def _on_next_card(self) -> None:
        if self.current_preview_index < len(self.generated_cards) - 1:
            self.current_preview_index += 1
            self._update_preview()

    @Slot()
    def _on_toggle_verso(self) -> None:
        self.verso_visible = not self.verso_visible
        icon_name = "ph.eye" if not self.verso_visible else "ph.eye-slash"
        self.preview_widget.btn_toggle_verso.setIcon(load_phosphor_icon(icon_name, color=DesignTokens.TEXT_PRIMARY))
        self._update_preview()

    @Slot()
    def _on_validate_card(self) -> None:
        if self.generated_cards:
            self.generated_cards[self.current_preview_index]["status"] = "VALIDÉ"
            self._update_table()

    @Slot()
    def _on_edit_card(self) -> None:
        pass

    @Slot()
    def _on_reject_card(self) -> None:
        if self.generated_cards:
            self.generated_cards.pop(self.current_preview_index)
            if self.current_preview_index >= len(self.generated_cards):
                self.current_preview_index = max(0, len(self.generated_cards) - 1)
            self._update_table()
            self._update_preview()

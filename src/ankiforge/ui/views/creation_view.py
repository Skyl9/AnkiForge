"""
Studio de Création AnkiForge — 100% Conforme aux Exigences & Raccordement Métier (master).
- Sélection des paquets raccordée à DeckModel.select() + sélecteur et création dynamique (+ Nouveau).
- Détection et auto-seeding automatique des Moteurs IA (LLMConfigModel) avec affichage display_name.
- Détection et auto-seeding automatique des Pipelines Agentiques (PipelineModel).
- Carte visuelle interactive cliquable pour l'Activation de la Vision (PDF / Schémas / Figures) avec retours visuels dorés.
- Sélection de documents (DocumentModel) avec gestion du cas vide -> bouton "Mes Documents" + bouton "Coller le presse-papiers".
- Intégration complète CreationWorker, NoteManager.create_note et CardPreviewWidget.
"""

import json
import logging
from typing import Any, Optional

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
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
    StyledTableWidget,
    StyledTextEdit,
)
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.card_preview_widget import CardPreviewWidget
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class VisionCard(QFrame):
    """Carte interactive cliquable pour l'activation du mode Vision."""

    clicked = Signal()

    def mousePressEvent(self, event: Any) -> None:
        super().mousePressEvent(event)
        self.clicked.emit()


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
    Studio de Création AnkiForge.
    Signal request_navigation(str) pour basculer vers d'autres vues (documents, pipelines, settings).
    """

    request_navigation = Signal(str)

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
        self.config_panel.setMinimumWidth(260)

        config_content = QWidget()
        config_layout = QVBoxLayout(config_content)
        config_layout.setContentsMargins(12, 12, 12, 12)
        config_layout.setSpacing(12)

        def add_form_group(layout: QVBoxLayout, label_text: str, widget_or_layout: Any) -> None:
            lbl = QLabel(label_text)
            lbl.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-weight: 600; font-size: 11px;")
            layout.addWidget(lbl)
            if isinstance(widget_or_layout, QWidget):
                layout.addWidget(widget_or_layout)
            else:
                layout.addLayout(widget_or_layout)

        # 1. Paquet Cible (Deck) + Bouton Nouveau
        deck_row = QHBoxLayout()
        deck_row.setSpacing(6)
        self.deck_combo = StyledComboBox()
        self.btn_new_deck = IconButton("ph.plus", tooltip="Créer un nouveau paquet Anki", size=20)
        deck_row.addWidget(self.deck_combo, 1)
        deck_row.addWidget(self.btn_new_deck)
        add_form_group(config_layout, "PAQUET CIBLE :", deck_row)

        # 2. Modèle de Carte
        self.model_combo = StyledComboBox()
        self.model_combo.currentIndexChanged.connect(self._on_model_changed)
        add_form_group(config_layout, "MODÈLE DE CARTE :", self.model_combo)

        # 3. Moteur IA + Bouton d'aide si vide
        self.engine_combo = StyledComboBox()
        add_form_group(config_layout, "MOTEUR IA :", self.engine_combo)

        self.btn_no_engine_help = SecondaryButton("⚙️ Configurer les Moteurs IA")
        self.btn_no_engine_help.setStyleSheet("color: #eab308; border-color: rgba(234, 179, 8, 0.4); font-size: 11px;")
        self.btn_no_engine_help.hide()
        config_layout.addWidget(self.btn_no_engine_help)

        # 4. Pipeline Agentique + Bouton d'aide si vide
        self.pipeline_combo = StyledComboBox()
        add_form_group(config_layout, "PIPELINE AGENTIQUE :", self.pipeline_combo)

        self.btn_no_pipeline_help = SecondaryButton("🔀 Créer un Pipeline d'Agents")
        self.btn_no_pipeline_help.setStyleSheet("color: #a855f7; border-color: rgba(168, 85, 247, 0.4); font-size: 11px;")
        self.btn_no_pipeline_help.hide()
        config_layout.addWidget(self.btn_no_pipeline_help)

        # 5. Carte Visuelle Interactive : Activation de la Vision
        self.vision_card = VisionCard()
        self.vision_card.setCursor(Qt.CursorShape.PointingHandCursor)
        vision_layout = QVBoxLayout(self.vision_card)
        vision_layout.setContentsMargins(10, 10, 10, 10)
        vision_layout.setSpacing(6)

        vision_top = QHBoxLayout()
        self.lbl_vision_icon = QLabel()
        self.lbl_vision_icon.setPixmap(load_phosphor_icon("ph.eye", color="#eab308").pixmap(20, 20))
        self.lbl_vision_title = QLabel("Analyse Vision (PDF & Images)")
        self.lbl_vision_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: bold; font-size: 12px;")

        self.vision_badge = Badge("DÉSACTIVÉE", variant="neutral")

        vision_top.addWidget(self.lbl_vision_icon)
        vision_top.addWidget(self.lbl_vision_title)
        vision_top.addStretch()
        vision_top.addWidget(self.vision_badge)
        vision_layout.addLayout(vision_top)

        self.lbl_vision_desc = QLabel("Activer l'extraction multimodale des schémas, figures & tableaux PDF.")
        self.lbl_vision_desc.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px;")
        self.lbl_vision_desc.setWordWrap(True)
        vision_layout.addWidget(self.lbl_vision_desc)

        self.vision_cb = QCheckBox()
        self.vision_cb.hide()  # Géré via l'interaction de la carte
        vision_layout.addWidget(self.vision_cb)

        config_layout.addWidget(self.vision_card)

        config_layout.addStretch()

        moteur_content = QWidget()
        moteur_layout = QVBoxLayout(moteur_content)
        moteur_layout.setContentsMargins(12, 12, 12, 12)
        moteur_lbl = QLabel("Configuration avancée du LLM (Température, Top P, Max Tokens).")
        moteur_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 12px;")
        moteur_lbl.setWordWrap(True)
        moteur_layout.addWidget(moteur_lbl)
        moteur_layout.addStretch()

        self.config_panel.add_tab("Configuration IA Studio", config_content, "ph.cpu", closable=False)
        self.config_panel.add_tab("Paramètres Moteur Studio", moteur_content, "ph.gear", closable=False)

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

        # Document Selector Toolbar + Actions
        source_top_toolbar = QHBoxLayout()
        self.doc_selector = StyledComboBox()
        source_top_toolbar.addWidget(self.doc_selector, 1)

        self.btn_refresh = IconButton("ph.arrows-clockwise", tooltip="Actualiser la liste des documents", size=24)
        self.btn_refresh.clicked.connect(self.refresh_data)
        source_top_toolbar.addWidget(self.btn_refresh)

        self.btn_go_docs = SecondaryButton("📁 Mes Documents")
        self.btn_go_docs.setIcon(load_phosphor_icon("ph.folder", color=DesignTokens.TEXT_PRIMARY))
        self.btn_go_docs.hide()
        source_top_toolbar.addWidget(self.btn_go_docs)

        self.btn_paste_clipboard = SecondaryButton("Coller le presse-papiers")
        self.btn_paste_clipboard.setIcon(load_phosphor_icon("ph.clipboard", color=DesignTokens.TEXT_PRIMARY))
        source_top_toolbar.addWidget(self.btn_paste_clipboard)

        source_layout.addLayout(source_top_toolbar)

        self.source_text_edit = StyledTextEdit()
        self.source_text_edit.setPlaceholderText("📝 Saisissez ou collez directement votre extrait de cours ici (ex: notes de cours, résumés, chapitres PDF)...")
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

        self.source_panel.add_tab("Document Source Studio", source_content, "ph.text-align-left", closable=False)
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

        self.results_panel.add_tab("Cartes Générées Studio", cartes_content, "ph.list-numbers", closable=False)
        self.results_panel.add_tab("Journal des Erreurs Studio", erreurs_content, "ph.warning-circle", closable=False)

        self.center_splitter.addWidget(self.results_panel)
        self.center_splitter.setSizes([320, 480])
        self.main_splitter.setSizes([260, 800])

        self._update_vision_ui(False)

    def _connect_signals(self) -> None:
        self.source_text_edit.textChanged.connect(self._on_text_changed)
        self.doc_selector.currentIndexChanged.connect(self._on_document_selected)
        self.btn_paste_clipboard.clicked.connect(self._on_paste_clipboard)

        self.vision_card.clicked.connect(self._toggle_vision_card)
        self.vision_cb.toggled.connect(self._update_vision_ui)

        self.btn_new_deck.clicked.connect(self._on_create_new_deck)
        self.btn_no_engine_help.clicked.connect(self._open_settings_modal)
        self.btn_no_pipeline_help.clicked.connect(lambda: self.request_navigation.emit("pipelines"))
        self.btn_go_docs.clicked.connect(lambda: self.request_navigation.emit("documents"))

        self.btn_generate.clicked.connect(self._on_generate)
        self.btn_cancel.clicked.connect(self._on_cancel_generation)
        self.btn_save_anki.clicked.connect(self._on_save_anki)

        self.preview_widget.btn_prev.clicked.connect(self._on_prev_card)
        self.preview_widget.btn_next.clicked.connect(self._on_next_card)
        self.preview_widget.btn_toggle_verso.clicked.connect(self._on_toggle_verso)
        self.preview_widget.btn_valider.clicked.connect(self._on_validate_card)
        self.preview_widget.btn_editer.clicked.connect(self._on_edit_card)
        self.preview_widget.btn_rejeter.clicked.connect(self._on_reject_card)

    def _toggle_vision_card(self) -> None:
        self.vision_cb.setChecked(not self.vision_cb.isChecked())

    @Slot(bool)
    def _update_vision_ui(self, checked: bool) -> None:
        if checked:
            self.vision_card.setStyleSheet("""
                QFrame {
                    background-color: rgba(234, 179, 8, 0.12);
                    border: 1px solid #eab308;
                    border-radius: 6px;
                }
            """)
            self.lbl_vision_icon.setPixmap(load_phosphor_icon("ph.eye", color="#eab308").pixmap(20, 20))
            badge_style = "background-color: rgba(234, 179, 8, 0.25); " "color: #eab308; border: 1px solid #eab308; " "font-weight: bold; padding: 2px 6px; " "border-radius: 4px; font-size: 10px;"
            self.vision_badge.setStyleSheet(badge_style)
            self.lbl_vision_desc.setText("Analyse multimodale active — Prise en charge des PDF, schémas, formules et figures.")
            show_toast(self, "Analyse Vision IA activée !")
        else:
            self.vision_card.setStyleSheet(f"""
                QFrame {{
                    background-color: #1a1d24;
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    border-radius: 6px;
                }}
            """)
            self.lbl_vision_icon.setPixmap(load_phosphor_icon("ph.eye-closed", color=DesignTokens.TEXT_MUTED).pixmap(20, 20))
            self.vision_badge.setText("DÉSACTIVÉE")
            badge_style_off = (
                f"background-color: #2d313a; color: {DesignTokens.TEXT_MUTED}; " f"border: 1px solid {DesignTokens.BORDER_COLOR}; " "padding: 2px 6px; border-radius: 4px; font-size: 10px;"
            )
            self.vision_badge.setStyleSheet(badge_style_off)
            self.lbl_vision_desc.setText("Activer l'extraction visuelle des schémas, tableaux & figures PDF.")

    def refresh_data(self) -> None:
        """Recharge les données dynamiques depuis Peewee DB (Decks, NoteTypes, Engines, Pipelines, Docs)."""
        try:
            # 1. Decks (Paquets existants + sélecteur)
            self.deck_combo.blockSignals(True)
            self.deck_combo.clear()
            decks = list(DeckModel.select())
            if not decks:
                DeckModel.get_or_create(name="Général")
                decks = list(DeckModel.select())
            for dk in decks:
                self.deck_combo.addItem(f"🎴 {dk.name}", userData=dk)
            self.deck_combo.blockSignals(False)

            # 2. Note Types
            self.model_combo.blockSignals(True)
            self.model_combo.clear()
            note_types = list(NoteTypeModel.select())
            if note_types:
                for nt in note_types:
                    self.model_combo.addItem(f"📝 {nt.name}", userData=nt)
            else:
                self.model_combo.addItem("📝 Basique (Recto/Verso)", userData=None)
                self.model_combo.addItem("📝 Texte à trous (Cloze)", userData=None)
            self.model_combo.blockSignals(False)

            # 3. Engines LLM
            self.engine_combo.blockSignals(True)
            self.engine_combo.clear()
            engines = list(LLMConfigModel.select())
            if not engines:
                LLMConfigModel.create(
                    display_name="GPT-4o (OpenAI)",
                    provider="openai",
                    model_id="gpt-4o",
                    context_limit=128000,
                )
                LLMConfigModel.create(
                    display_name="Claude 3.5 Sonnet (Anthropic)",
                    provider="anthropic",
                    model_id="claude-3-5-sonnet-20240620",
                    context_limit=200000,
                )
                engines = list(LLMConfigModel.select())

            for eg in engines:
                display_name = getattr(eg, "display_name", getattr(eg, "name", str(eg)))
                self.engine_combo.addItem(f"⚡ {display_name}", userData=eg)
            self.btn_no_engine_help.hide()
            self.engine_combo.blockSignals(False)

            # 4. Pipelines
            self.pipeline_combo.blockSignals(True)
            self.pipeline_combo.clear()
            pipelines = list(PipelineModel.select())
            if not pipelines:
                p1 = PipelineModel.create(
                    name="Excellence Math/Info (Archiviste + Linter)",
                    description="Pipeline haute-fidélité pour les cours scientifiques.",
                )
                pipelines = [p1]

            for pipe in pipelines:
                self.pipeline_combo.addItem(f"🔀 {pipe.name}", userData=pipe)
            self.btn_no_pipeline_help.hide()
            self.pipeline_combo.blockSignals(False)

            # 5. Documents
            self.doc_selector.blockSignals(True)
            self.doc_selector.clear()
            docs = list(DocumentModel.select())
            if docs:
                self.doc_selector.addItem("-- Sélectionner un document existant --", userData=None)
                for doc in docs:
                    self.doc_selector.addItem(f"📄 {doc.title}", userData=doc)
                self.btn_go_docs.hide()
            else:
                self.doc_selector.addItem("⚠️ Aucun document en bibliothèque (Coller du texte ci-dessous)", userData=None)
                self.btn_go_docs.show()
            self.doc_selector.blockSignals(False)

            self._on_model_changed()

        except Exception as e:
            logger.warning("Erreur lors de la mise à jour des combos creation_view: %s", e, exc_info=True)

    def is_dirty(self) -> bool:
        return len(self.generated_cards) > 0

    @Slot()
    def _on_create_new_deck(self) -> None:
        name, ok = QInputDialog.getText(self, "Nouveau Paquet", "Nom du paquet Anki (ex: Science::Physique) :")
        if ok and name.strip():
            try:
                dk_name = name.strip()
                DeckModel.create(name=dk_name, description="Nouveau paquet créé depuis le Studio.")
                self.refresh_data()
                idx = self.deck_combo.findText(f"🎴 {dk_name}", Qt.MatchFlag.MatchFixedString)
                if idx != -1:
                    self.deck_combo.setCurrentIndex(idx)
                show_toast(self, f"Paquet '{dk_name}' créé avec succès !")
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Impossible de créer le paquet : {str(e)}")

    @Slot()
    def _open_settings_modal(self) -> None:
        from ankiforge.ui.widgets.settings_modal import SettingsModal

        modal = SettingsModal(ai_manager=self.ai_manager, parent=self)
        modal.exec()

    @Slot()
    def _on_paste_clipboard(self) -> None:
        clipboard = QApplication.clipboard()
        text = clipboard.text().strip()
        if text:
            self.source_text_edit.setPlainText(text)
            show_toast(self, "Texte collé depuis le presse-papiers !")
        else:
            show_toast(self, "Le presse-papiers est vide.", is_error=True)

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

        if not selected_engine:
            show_toast(self, "Aucun moteur IA configuré. Veuillez configurer les clés API dans les paramètres.", is_error=True)
            return

        nt_id = selected_nt.id if selected_nt and hasattr(selected_nt, "id") else 1
        nt_schema = json.loads(selected_nt.fields_schema) if selected_nt and hasattr(selected_nt, "fields_schema") and selected_nt.fields_schema else ["Front", "Back"]

        pipe_id = selected_pipeline.id if selected_pipeline and hasattr(selected_pipeline, "id") else 1
        pipe_name = selected_pipeline.name if selected_pipeline and hasattr(selected_pipeline, "name") else "Standard"

        pipeline_steps = []
        if selected_pipeline and hasattr(selected_pipeline, "steps"):
            pipeline_steps = [s.agent.name for s in selected_pipeline.steps if s.agent]

        payload = CreationTaskPayload(
            text_source=text_source,
            note_type_id=nt_id,
            note_type_fields_schema=nt_schema,
            pipeline_id=pipe_id,
            pipeline_name=pipe_name,
            pipeline_steps=pipeline_steps,
            use_vision=self.vision_cb.isChecked(),
        )

        provider = None
        if self.ai_manager and hasattr(self.ai_manager, "create_provider_from_config"):
            try:
                provider = self.ai_manager.create_provider_from_config(selected_engine)
            except Exception as e:
                logger.warning("Impossible de créer le provider depuis la config: %s", e)

        self.btn_generate.setEnabled(False)
        self.btn_cancel.show()

        self.worker = CreationWorker(ai_provider=provider, payload=payload)
        self.worker.progress.connect(self._on_worker_progress)
        self.worker.log.connect(self._on_worker_log)
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.error.connect(self._on_worker_error)
        self.worker.cancelled.connect(self._on_worker_cancelled)
        self.worker.start()

    @Slot(int)
    def _on_worker_progress(self, val: int) -> None:
        pass

    @Slot(str)
    def _on_worker_log(self, msg: str) -> None:
        logger.info("[CreationWorker] %s", msg)

    @Slot(list)
    def _on_worker_finished(self, cards: list[dict[str, Any]]) -> None:
        self.btn_generate.setEnabled(True)
        self.btn_cancel.hide()
        self.generated_cards = cards
        self.current_preview_index = 0

        self._populate_results_table()
        self._update_card_preview()
        show_toast(self, f"{len(cards)} cartes générées avec succès !")

    @Slot(str)
    def _on_worker_error(self, err_msg: str) -> None:
        self.btn_generate.setEnabled(True)
        self.btn_cancel.hide()
        self.err_lbl.setText(f"⚠️ Erreur de génération : {err_msg}")
        self.results_panel.set_tab_title(1, "Journal des Erreurs (1)")
        show_toast(self, f"Erreur : {err_msg}", is_error=True)

    @Slot()
    def _on_worker_cancelled(self) -> None:
        self.btn_generate.setEnabled(True)
        self.btn_cancel.hide()
        show_toast(self, "Génération annulée par l'utilisateur.")

    @Slot()
    def _on_cancel_generation(self) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.cancel()

    def _populate_results_table(self) -> None:
        self.results_table.blockSignals(True)
        self.results_table.setRowCount(len(self.generated_cards))

        col_count = self.results_table.columnCount()

        for row, card in enumerate(self.generated_cards):
            card["status"] = card.get("status", "À valider")
            front_text = card.get("Front", card.get("Recto", ""))
            back_text = card.get("Back", card.get("Verso", ""))

            self.results_table.setItem(row, 0, QTableWidgetItem(front_text))
            if col_count > 2:
                self.results_table.setItem(row, 1, QTableWidgetItem(back_text))
                self.results_table.setItem(row, col_count - 1, QTableWidgetItem(card["status"]))
            else:
                self.results_table.setItem(row, 1, QTableWidgetItem(card["status"]))

        self.results_table.blockSignals(False)

        if self.generated_cards:
            self.results_table.selectRow(0)

    def _update_card_preview(self) -> None:
        total = len(self.generated_cards)
        if total == 0:
            self.preview_widget.lbl_counter.setText("0 / 0")
            return

        self.current_preview_index = max(0, min(self.current_preview_index, total - 1))
        self.preview_widget.lbl_counter.setText(f"{self.current_preview_index + 1} / {total}")

        card = self.generated_cards[self.current_preview_index]
        selected_nt = self.model_combo.currentData()

        override_templates = None
        if not self.verso_visible:
            qfmt = card.get("Front", card.get("Recto", "{{Front}}"))
            override_templates = [{"name": "Carte 1", "qfmt": qfmt, "afmt": ""}]

        self.preview_widget.card_preview_widget.update_preview(
            note_type=selected_nt,
            fields_dict=card,
            override_templates=override_templates,
        )

    @Slot()
    def _on_table_selection_changed(self) -> None:
        selected_rows = self.results_table.selectedItems()
        if selected_rows:
            row = self.results_table.row(selected_rows[0])
            if 0 <= row < len(self.generated_cards):
                self.current_preview_index = row
                self._update_card_preview()

    @Slot(QTableWidgetItem)
    def _on_cell_edited(self, item: QTableWidgetItem) -> None:
        row = item.row()
        col = item.column()
        if 0 <= row < len(self.generated_cards):
            text = item.text()
            if col == 0:
                self.generated_cards[row]["Front"] = text
            elif col == 1 and self.results_table.columnCount() > 2:
                self.generated_cards[row]["Back"] = text
            self._update_card_preview()

    @Slot()
    def _on_prev_card(self) -> None:
        if self.current_preview_index > 0:
            self.current_preview_index -= 1
            self.results_table.selectRow(self.current_preview_index)
            self._update_card_preview()

    @Slot()
    def _on_next_card(self) -> None:
        if self.current_preview_index < len(self.generated_cards) - 1:
            self.current_preview_index += 1
            self.results_table.selectRow(self.current_preview_index)
            self._update_card_preview()

    @Slot()
    def _on_toggle_verso(self) -> None:
        self.verso_visible = not self.verso_visible
        label = "Masquer Verso" if self.verso_visible else "Afficher Verso"
        icon_name = "ph.eye-slash" if self.verso_visible else "ph.eye"
        self.preview_widget.btn_toggle_verso.setText(label)
        self.preview_widget.btn_toggle_verso.setIcon(load_phosphor_icon(icon_name, color=DesignTokens.TEXT_PRIMARY))
        self._update_card_preview()

    @Slot()
    def _on_validate_card(self) -> None:
        if self.generated_cards and 0 <= self.current_preview_index < len(self.generated_cards):
            self.generated_cards[self.current_preview_index]["status"] = "Validée"
            self._populate_results_table()
            show_toast(self, "Carte validée avec succès !")

    @Slot()
    def _on_edit_card(self) -> None:
        if not self.generated_cards or not (0 <= self.current_preview_index < len(self.generated_cards)):
            return

        card = self.generated_cards[self.current_preview_index]
        dlg = CardEditDialog(
            front=card.get("Front", card.get("Recto", "")),
            back=card.get("Back", card.get("Verso", "")),
            parent=self,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_front, new_back = dlg.get_data()
            card["Front"] = new_front
            card["Back"] = new_back
            self._populate_results_table()
            self._update_card_preview()
            show_toast(self, "Carte mise à jour !")

    @Slot()
    def _on_reject_card(self) -> None:
        if self.generated_cards and 0 <= self.current_preview_index < len(self.generated_cards):
            removed = self.generated_cards.pop(self.current_preview_index)
            self._populate_results_table()
            self._update_card_preview()
            show_toast(self, f"Carte '{removed.get('Front', '')[:20]}...' rejetée.")

    @Slot()
    def _on_save_anki(self) -> None:
        if not self.generated_cards:
            show_toast(self, "Aucune carte générée à sauvegarder.", is_error=True)
            return

        selected_nt = self.model_combo.currentData()
        deck_data = self.deck_combo.currentData()
        deck_name = deck_data.name if deck_data and hasattr(deck_data, "name") else self.deck_combo.currentText().replace("🎴 ", "")

        saved_count = 0
        try:
            for card in self.generated_cards:
                if card.get("status") != "Rejetée":
                    front = card.get("Front", card.get("Recto", ""))
                    back = card.get("Back", card.get("Verso", ""))
                    fields = {"Front": front, "Back": back}

                    deck_obj, _ = DeckModel.get_or_create(name=deck_name)
                    NoteManager.create_note(
                        note_type=selected_nt,
                        deck=deck_obj,
                        content_dict=fields,
                        tags=["ankiforge_generated"],
                        source="ai",
                    )
                    saved_count += 1

            show_toast(self, f"{saved_count} cartes enregistrées dans Anki/Peewee DB !")
        except Exception as e:
            logger.exception("Erreur lors de la sauvegarde dans Anki: %s", e)
            QMessageBox.critical(self, "Erreur de Sauvegarde", f"Échec de l'enregistrement dans Anki : {str(e)}")


CreationTab = CreationView

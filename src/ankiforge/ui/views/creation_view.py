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
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QSlider,
    QSplitter,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import (
    DeckModel,
    DocumentModel,
    FolderModel,
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
from ankiforge.ui.dialogs.selection_dialog import SelectionDialog
from ankiforge.ui.dialogs.deck_selection_dialog import DeckSelectionDialog
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem

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

        layout.addLayout(top_toolbar)

        # Intégration de CardPreviewWidget (Moteur WebEngine + MathJax + multi-appareils)
        self.card_preview_widget = CardPreviewWidget(show_header=False)
        layout.addWidget(self.card_preview_widget, 1)

        # Les boutons ont été déplacés dans la vue principale (CreationView) pour être globaux au panneau.
        layout.addWidget(self.card_preview_widget, 1)


class DocumentEditorWidget(QWidget):
    """Conteneur pour l'éditeur de texte source et la barre d'outils de génération associée."""

    generate_requested = Signal(str)
    cancel_requested = Signal()

    def __init__(self, content: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self.editor = StyledTextEdit()
        self.editor.setStyleSheet(f"font-family: '{DesignTokens.FONT_CODE}';")
        self.editor.setPlaceholderText("📝 Saisissez ou collez directement votre extrait de cours ici (ex: notes de cours, résumés, chapitres PDF)...")
        self.editor.setPlainText(content)
        self.editor.textChanged.connect(self._on_text_changed)
        layout.addWidget(self.editor, 1)

        bot_widget = QWidget()
        bot_widget.setStyleSheet("background: transparent;")
        bot_layout = QHBoxLayout(bot_widget)
        bot_layout.setContentsMargins(0, 8, 0, 0)

        self.tokens_lbl = QLabel("Aa 0 chars  |  ~0 Tokens")
        self.tokens_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-family: '{DesignTokens.FONT_CODE}'; font-size: 11px;")
        bot_layout.addWidget(self.tokens_lbl)
        bot_layout.addStretch()

        self.btn_paste = SecondaryButton("Coller")
        self.btn_paste.setIcon(load_phosphor_icon("ph.clipboard", color=DesignTokens.TEXT_PRIMARY))
        self.btn_paste.clicked.connect(self.editor.paste)

        self.btn_generate = PrimaryButton("Générer (Ctrl+Enter)")
        self.btn_generate.setIcon(load_phosphor_icon("ph.play", color="white"))
        self.btn_generate.clicked.connect(self._on_generate_clicked)

        self.btn_cancel = DangerButton("Arrêter", ghost=True)
        self.btn_cancel.setIcon(load_phosphor_icon("ph.stop-circle", color=DesignTokens.COLOR_RED))
        self.btn_cancel.hide()
        self.btn_cancel.clicked.connect(self.cancel_requested.emit)

        bot_layout.addWidget(self.btn_paste)
        bot_layout.addWidget(self.btn_generate)
        bot_layout.addWidget(self.btn_cancel)
        layout.addWidget(bot_widget)

        self._on_text_changed()

    @Slot()
    def _on_text_changed(self) -> None:
        text = self.editor.toPlainText()
        chars = len(text)
        words = len(text.split())
        estimated_tokens = int(words * 1.3)
        self.tokens_lbl.setText(f"Aa {chars} chars  |  ~{estimated_tokens} Tokens")

    @Slot()
    def _on_generate_clicked(self) -> None:
        self.generate_requested.emit(self.editor.toPlainText().strip())

    def get_text(self) -> str:
        return self.editor.toPlainText().strip()

    def set_generation_state(self, is_generating: bool) -> None:
        self.btn_generate.setEnabled(not is_generating)
        if is_generating:
            self.btn_generate.hide()
            self.btn_cancel.show()
        else:
            self.btn_generate.show()
            self.btn_cancel.hide()


class CreationView(QWidget):
    """
    Studio de Création AnkiForge.
    Signal request_navigation(str) pour basculer vers d'autres vues (documents, pipelines, settings).
    """

    request_navigation = Signal(str, object)

    def __init__(self, ai_manager: Any = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.ai_manager = ai_manager
        self.generated_cards: list[dict[str, Any]] = []
        self.current_preview_index = 0
        self.worker: Optional[CreationWorker] = None
        self.current_deck: Optional[DeckModel] = None
        self.current_model: Optional[NoteTypeModel] = None

        self.decks_cache: list[DeckModel] = []
        self.models_cache: list[NoteTypeModel] = []
        self.open_editors: dict[str, DocumentEditorWidget] = {}

        self._setup_ui()
        self._connect_signals()
        self.refresh_data()

    def _navigate(self, view_id: str, data: Optional[dict] = None) -> None:
        self.request_navigation.emit(view_id, data)

    def _setup_ui(self) -> None:
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(self.main_splitter)

        # --- COL 1: Left Tool Window (Explorateur + Config IA) ---
        self.config_panel = IdePanel(detachable=True)
        self.config_panel.setMinimumWidth(260)
        self.config_panel.setStyleSheet(f"border-right: 1px solid {DesignTokens.BORDER_COLOR};")

        # Tab 1: Explorateur
        explorer_content = QWidget()
        explorer_layout = QVBoxLayout(explorer_content)
        explorer_layout.setContentsMargins(10, 10, 10, 10)
        explorer_layout.setSpacing(8)

        self.btn_new_free_input = SecondaryButton("Nouvelle Saisie Libre")
        self.btn_new_free_input.setIcon(load_phosphor_icon("ph.plus", color=DesignTokens.TEXT_PRIMARY))
        explorer_layout.addWidget(self.btn_new_free_input)

        self.file_tree = QTreeWidget()
        self.file_tree.setHeaderHidden(True)
        self.file_tree.setStyleSheet(f"""
            QTreeWidget {{
                background-color: transparent;
                border: none;
                color: {DesignTokens.TEXT_PRIMARY};
            }}
            QTreeWidget::item {{
                padding: 4px;
                border-radius: 4px;
            }}
            QTreeWidget::item:hover {{
                background-color: {DesignTokens.BG_HOVER};
            }}
            QTreeWidget::item:selected {{
                background-color: {DesignTokens.BG_ACTIVE};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
        """)
        explorer_layout.addWidget(self.file_tree)

        # Tab 2: Config IA
        config_content = QWidget()
        config_layout = QVBoxLayout(config_content)
        config_layout.setContentsMargins(12, 12, 12, 12)
        config_layout.setSpacing(16)

        def add_form_group(layout: QVBoxLayout, label_text: str, widget_or_layout: Any) -> None:
            lbl = QLabel(label_text)
            lbl.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-weight: 600; font-size: 11px;")
            layout.addWidget(lbl)
            if isinstance(widget_or_layout, QWidget):
                layout.addWidget(widget_or_layout)
            else:
                layout.addLayout(widget_or_layout)

        # 1. Paquet Cible (Bouton Sélecteur)
        self.btn_select_deck = SecondaryButton("Sélectionner un paquet...")
        self.btn_select_deck.setIcon(load_phosphor_icon("ph.folder-open", color=DesignTokens.TEXT_MUTED))
        self.btn_select_deck.setStyleSheet(
            f"text-align: left; padding: 6px 10px; border-radius: 4px; border: 1px solid {DesignTokens.BORDER_COLOR}; background: {DesignTokens.BG_INPUT}; font-weight: normal;"
        )
        add_form_group(config_layout, "PAQUET CIBLE", self.btn_select_deck)

        # 2. Modèle de Carte (Bouton Sélecteur)
        self.btn_select_model = SecondaryButton("Sélectionner un modèle...")
        self.btn_select_model.setIcon(load_phosphor_icon("ph.file-code", color=DesignTokens.TEXT_MUTED))
        self.btn_select_model.setStyleSheet(
            f"text-align: left; padding: 6px 10px; border-radius: 4px; border: 1px solid {DesignTokens.BORDER_COLOR}; background: {DesignTokens.BG_INPUT}; font-weight: normal;"
        )
        add_form_group(config_layout, "MODÈLE DE CARTE", self.btn_select_model)

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
        self.vision_card.setObjectName("visionCard")
        self.vision_card.setStyleSheet(f"""
            QFrame#visionCard {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
            }}
            QFrame#visionCard:hover {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        self.vision_card.setCursor(Qt.CursorShape.PointingHandCursor)
        vision_layout = QVBoxLayout(self.vision_card)
        vision_layout.setContentsMargins(12, 12, 12, 12)
        vision_layout.setSpacing(6)

        vision_top = QHBoxLayout()
        self.lbl_vision_icon = QLabel()
        self.lbl_vision_icon.setPixmap(load_phosphor_icon("ph.eye-closed", color=DesignTokens.TEXT_MUTED).pixmap(16, 16))
        self.lbl_vision_title = QLabel("Vision (PDF)")
        self.lbl_vision_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: 600; font-size: 12px;")

        self.vision_badge = Badge("OFF", variant="neutral")

        vision_top.addWidget(self.lbl_vision_icon)
        vision_top.addWidget(self.lbl_vision_title)
        vision_top.addStretch()
        vision_top.addWidget(self.vision_badge)
        vision_layout.addLayout(vision_top)

        self.lbl_vision_desc = QLabel("Extraction multimodale des schémas & figures.")
        self.lbl_vision_desc.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")
        self.lbl_vision_desc.setWordWrap(True)
        vision_layout.addWidget(self.lbl_vision_desc)

        self.vision_cb = QCheckBox()
        self.vision_cb.hide()  # Géré via l'interaction de la carte
        vision_layout.addWidget(self.vision_cb)

        config_layout.addWidget(self.vision_card)

        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        separator.setStyleSheet(f"border: 1px dashed {DesignTokens.BORDER_COLOR}; margin: 8px 0;")
        config_layout.addWidget(separator)

        # Paramètres Avancés
        self.btn_toggle_advanced = QPushButton()
        self.btn_toggle_advanced.setStyleSheet("background: transparent; border: none; text-align: left; padding: 0;")
        self.btn_toggle_advanced.setCursor(Qt.CursorShape.PointingHandCursor)

        advanced_header = QHBoxLayout(self.btn_toggle_advanced)
        advanced_header.setContentsMargins(0, 0, 0, 0)
        advanced_lbl = QLabel("Paramètres Avancés")
        advanced_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; background: transparent;")

        self.advanced_icon = QLabel()
        self.advanced_icon.setPixmap(load_phosphor_icon("ph.caret-right", color=DesignTokens.TEXT_MUTED).pixmap(14, 14))
        self.advanced_icon.setStyleSheet("background: transparent;")

        advanced_header.addWidget(advanced_lbl)
        advanced_header.addStretch()
        advanced_header.addWidget(self.advanced_icon)

        config_layout.addWidget(self.btn_toggle_advanced)

        self.advanced_container = QFrame()
        self.advanced_container.setObjectName("advancedContainer")
        self.advanced_container.setVisible(False)
        self.advanced_container.setStyleSheet(f"""
            QFrame#advancedContainer {{
                background: rgba(0,0,0,0.1);
                padding: 12px;
                border-radius: 4px;
                border: 1px solid {DesignTokens.BORDER_COLOR};
            }}
        """)
        advanced_layout = QVBoxLayout(self.advanced_container)
        advanced_layout.setContentsMargins(0, 0, 0, 0)
        advanced_layout.setSpacing(12)

        # Style partagé des sliders
        slider_style = f"""
            QSlider::groove:horizontal {{
                border-radius: 2px;
                height: 4px;
                margin: 0px;
                background-color: rgba(255, 255, 255, 0.1);
            }}
            QSlider::sub-page:horizontal {{
                background-color: {DesignTokens.ACCENT_PRIMARY};
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background-color: {DesignTokens.ACCENT_PRIMARY};
                border: none;
                height: 12px;
                width: 12px;
                margin: -4px 0;
                border-radius: 6px;
            }}
            QSlider::handle:horizontal:hover {{
                background-color: {DesignTokens.ACCENT_HOVER};
            }}
        """

        # Température
        temp_layout = QVBoxLayout()
        temp_header = QHBoxLayout()
        temp_lbl = QLabel("Température")
        temp_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px;")
        self.val_temp_lbl = QLabel("0.7")
        self.val_temp_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-family: {DesignTokens.FONT_CODE}; font-size: 11px;")
        temp_header.addWidget(temp_lbl)
        temp_header.addStretch()
        temp_header.addWidget(self.val_temp_lbl)

        self.slider_temp = QSlider(Qt.Orientation.Horizontal)
        self.slider_temp.setMinimum(0)
        self.slider_temp.setMaximum(10)
        self.slider_temp.setValue(7)
        self.slider_temp.setStyleSheet(slider_style)
        self.slider_temp.valueChanged.connect(lambda v: self.val_temp_lbl.setText(f"{v/10:.1f}"))

        temp_layout.addLayout(temp_header)
        temp_layout.addWidget(self.slider_temp)
        advanced_layout.addLayout(temp_layout)

        # Max Tokens
        tokens_layout = QVBoxLayout()
        tokens_header = QHBoxLayout()
        tokens_lbl = QLabel("Max Tokens")
        tokens_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px;")
        self.val_tokens_lbl = QLabel("4096")
        self.val_tokens_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-family: {DesignTokens.FONT_CODE}; font-size: 11px;")
        tokens_header.addWidget(tokens_lbl)
        tokens_header.addStretch()
        tokens_header.addWidget(self.val_tokens_lbl)

        self.slider_tokens = QSlider(Qt.Orientation.Horizontal)
        self.slider_tokens.setMinimum(1)
        self.slider_tokens.setMaximum(32)
        self.slider_tokens.setValue(16)
        self.slider_tokens.setStyleSheet(slider_style)
        self.slider_tokens.valueChanged.connect(lambda v: self.val_tokens_lbl.setText(f"{v * 256}"))

        tokens_layout.addLayout(tokens_header)
        tokens_layout.addWidget(self.slider_tokens)
        advanced_layout.addLayout(tokens_layout)

        config_layout.addWidget(self.advanced_container)
        config_layout.addStretch()

        self.config_panel.add_tab("Explorateur", explorer_content, "ph.files", closable=False)
        self.config_panel.add_tab("Config IA", config_content, "ph.cpu", closable=False)

        self.main_splitter.addWidget(self.config_panel)

        # --- COL 2: Source + Results ---
        self.center_splitter = QSplitter(Qt.Orientation.Vertical)
        self.main_splitter.addWidget(self.center_splitter)

        # Panel Document Source
        source_container = QWidget()
        source_layout = QVBoxLayout(source_container)
        source_layout.setContentsMargins(0, 0, 0, 0)

        self.source_panel = IdePanel(detachable=True, tab_variant="document")
        source_layout.addWidget(self.source_panel)

        self.center_splitter.addWidget(source_container)

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
        # Bouton Sauvegarder retiré d'ici, déplacé dans la barre globale
        self.results_table.setSelectionBehavior(StyledTableWidget.SelectionBehavior.SelectRows)
        self.results_table.itemSelectionChanged.connect(self._on_table_selection_changed)
        self.results_table.itemChanged.connect(self._on_cell_edited)
        table_layout.addWidget(self.results_table, 1)

        self.results_splitter.addWidget(table_container)

        # Droite : Aperçu interactif WebEngine
        self.preview_widget = FlashcardPreview()
        self.results_splitter.addWidget(self.preview_widget)

        cartes_layout.addWidget(self.results_splitter, 1)

        # Barre d'actions globale (Footer du panneau Cartes Générées)
        main_bot_toolbar = QHBoxLayout()
        main_bot_toolbar.setContentsMargins(12, 0, 12, 12)

        self.btn_save_anki = PrimaryButton("Enregistrer dans la Forge")
        self.btn_save_anki.setIcon(load_phosphor_icon("ph.floppy-disk", color="white"))
        main_bot_toolbar.addWidget(self.btn_save_anki)

        main_bot_toolbar.addStretch()

        self.btn_rejeter = DangerButton("Rejeter", ghost=True)
        self.btn_rejeter.setIcon(load_phosphor_icon("ph.trash", color=DesignTokens.COLOR_RED))

        self.btn_editer = SecondaryButton("Éditer")
        self.btn_editer.setIcon(load_phosphor_icon("ph.pencil-simple", color=DesignTokens.TEXT_PRIMARY))

        self.btn_valider = PrimaryButton("Garder")
        self.btn_valider.setIcon(load_phosphor_icon("ph.check", color="white"))

        main_bot_toolbar.addWidget(self.btn_rejeter)
        main_bot_toolbar.addWidget(self.btn_editer)
        main_bot_toolbar.addWidget(self.btn_valider)

        cartes_layout.addLayout(main_bot_toolbar)

        erreurs_content = QWidget()
        erreurs_layout = QVBoxLayout(erreurs_content)
        erreurs_layout.setContentsMargins(12, 12, 12, 12)
        self.err_lbl = QLabel("Aucune erreur lors du processus de génération.")
        self.err_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 12px;")
        erreurs_layout.addWidget(self.err_lbl)
        erreurs_layout.addStretch()

        self.results_panel.add_tab("Cartes Générées (0)", cartes_content, "ph.list-numbers", closable=False)
        self.results_panel.add_tab("Journal des Erreurs", erreurs_content, "ph.warning-circle", closable=False)

        self.center_splitter.addWidget(self.results_panel)
        self.center_splitter.setSizes([320, 480])
        self.main_splitter.setSizes([260, 800])

        # Creation du tab initial
        self._open_document_tab("Saisie Libre")
        self._update_vision_ui(False)

    def _connect_signals(self) -> None:
        self.btn_new_free_input.clicked.connect(lambda: self._open_document_tab("Nouvelle Saisie"))
        self.file_tree.itemDoubleClicked.connect(self._on_explorer_item_double_clicked)

        self.btn_select_deck.clicked.connect(self._on_click_select_deck)
        self.btn_select_model.clicked.connect(self._on_click_select_model)

        self.vision_card.clicked.connect(self._toggle_vision_card)
        self.vision_cb.toggled.connect(self._update_vision_ui)
        self.btn_toggle_advanced.clicked.connect(self._toggle_advanced_settings)

        self.btn_no_engine_help.clicked.connect(self._open_settings_modal)
        self.btn_no_pipeline_help.clicked.connect(lambda: self._navigate("pipelines"))
        self.btn_save_anki.clicked.connect(self._on_save_anki)
        self.preview_widget.btn_prev.clicked.connect(self._on_prev_card)
        self.preview_widget.btn_next.clicked.connect(self._on_next_card)

        self.btn_valider.clicked.connect(self._on_validate_card)
        self.btn_editer.clicked.connect(self._on_edit_card)
        self.btn_rejeter.clicked.connect(self._on_reject_card)

    def _toggle_vision_card(self) -> None:
        self.vision_cb.setChecked(not self.vision_cb.isChecked())

    def _toggle_advanced_settings(self) -> None:
        is_visible = not self.advanced_container.isVisible()
        self.advanced_container.setVisible(is_visible)
        icon_name = "ph.caret-down" if is_visible else "ph.caret-right"
        self.advanced_icon.setPixmap(load_phosphor_icon(icon_name, color=DesignTokens.TEXT_MUTED).pixmap(14, 14))

    @Slot(bool)
    def _update_vision_ui(self, checked: bool) -> None:
        if checked:
            self.lbl_vision_icon.setPixmap(load_phosphor_icon("ph.eye", color="#eab308").pixmap(16, 16))
            self.vision_badge.setText("ON")
            self.vision_badge.set_variant("warning")
            self.vision_card.setStyleSheet("""
                QFrame#visionCard {
                    background-color: rgba(234, 179, 8, 0.1);
                    border: 1px solid #eab308;
                    border-radius: 6px;
                }
            """)
        else:
            self.lbl_vision_icon.setPixmap(load_phosphor_icon("ph.eye-closed", color=DesignTokens.TEXT_MUTED).pixmap(16, 16))
            self.vision_badge.setText("OFF")
            self.vision_badge.set_variant("neutral")
            self.vision_card.setStyleSheet(f"""
                QFrame#visionCard {{
                    background-color: {DesignTokens.BG_INPUT};
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    border-radius: 6px;
                }}
                QFrame#visionCard:hover {{
                    border-color: {DesignTokens.ACCENT_PRIMARY};
                }}
            """)

    def refresh_data(self) -> None:
        """Recharge les données dynamiques depuis Peewee DB (Decks, NoteTypes, Engines, Pipelines, Docs)."""
        try:
            # 1. Decks (Paquets existants + sélecteur)
            decks = list(DeckModel.select())
            if not decks:
                DeckModel.get_or_create(name="Général")
                decks = list(DeckModel.select())
            self.decks_cache = decks
            if self.current_deck is None and self.decks_cache:
                self._set_current_deck(self.decks_cache[0])

            # 2. Note Types
            note_types = list(NoteTypeModel.select())
            if not note_types:
                # Add default models if empty in cache for selection dialog
                class DummyModel:
                    def __init__(self, name: str):
                        self.name = name
                        self.fields_schema = ""

                note_types = [DummyModel("Basique (Recto/Verso)"), DummyModel("Texte à trous (Cloze)")]
            self.models_cache = note_types
            if self.current_model is None and self.models_cache:
                self._set_current_model(self.models_cache[0])

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

            # 5. Documents in Explorer Tree
            self.file_tree.clear()

            folders = list(FolderModel.select())
            docs = list(DocumentModel.select())

            folder_items: dict[int, QTreeWidgetItem] = {}
            for folder in folders:
                f_item = QTreeWidgetItem(self.file_tree)
                f_item.setText(0, folder.name)
                f_item.setIcon(0, load_phosphor_icon("folder", color=DesignTokens.ACCENT_PRIMARY, weight="fill"))
                f_item.setData(0, Qt.ItemDataRole.UserRole, folder)
                folder_items[folder.id] = f_item
                f_item.setExpanded(True)

            if not docs and not folders:
                item = QTreeWidgetItem(self.file_tree)
                item.setText(0, "Aucun document")
                item.setIcon(0, load_phosphor_icon("ph.warning-circle", color=DesignTokens.TEXT_MUTED))
            else:
                for doc in docs:
                    parent_item: Any = self.file_tree
                    if doc.folder_id and doc.folder_id in folder_items:
                        parent_item = folder_items[doc.folder_id]

                    item = QTreeWidgetItem(parent_item)
                    item.setText(0, doc.title)

                    if doc.title.lower().endswith(".pdf"):
                        item.setIcon(0, load_phosphor_icon("file-pdf", color=DesignTokens.COLOR_RED, weight="fill"))
                    elif doc.title.lower().endswith((".md", ".txt", ".json", ".csv")):
                        item.setIcon(0, load_phosphor_icon("file-code", color=DesignTokens.COLOR_YELLOW, weight="fill"))
                    else:
                        item.setIcon(0, load_phosphor_icon("file-text", color=DesignTokens.COLOR_GREEN, weight="fill"))

                    item.setData(0, Qt.ItemDataRole.UserRole, doc)

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
                new_deck, _ = DeckModel.get_or_create(name=dk_name, description="Nouveau paquet créé depuis le Studio.")
                self.refresh_data()
                self._set_current_deck(new_deck)
                show_toast(self, f"Paquet '{dk_name}' créé avec succès !")
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Impossible de créer le paquet : {str(e)}")

    @Slot()
    def _open_settings_modal(self) -> None:
        from ankiforge.ui.widgets.settings_modal import SettingsModal

        modal = SettingsModal(ai_manager=self.ai_manager, parent=self)
        modal.exec()

    def _open_document_tab(self, title: str, content: str = "", doc_model: Optional[Any] = None) -> None:
        # Create a unique title if multiple Saisie Libres are opened
        base_title = title
        counter = 1
        while title in self.open_editors:
            title = f"{base_title} {counter}"
            counter += 1

        editor_widget = DocumentEditorWidget(content, parent=self)
        editor_widget.generate_requested.connect(self._on_generate)
        editor_widget.cancel_requested.connect(self._on_cancel_generation)

        self.open_editors[title] = editor_widget
        icon = "ph.text-t"
        icon_color = DesignTokens.TEXT_SECONDARY

        if doc_model:
            title_lower = title.lower()
            if title_lower.endswith(".pdf"):
                icon = "ph.file-pdf"
                icon_color = DesignTokens.COLOR_RED
            elif title_lower.endswith((".md", ".txt", ".json", ".csv")):
                icon = "ph.file-code"
                icon_color = DesignTokens.COLOR_BLUE
            else:
                icon = "ph.file-text"
                icon_color = DesignTokens.COLOR_BLUE

        self.source_panel.register_tab(title, editor_widget, icon, closable=True, icon_color=icon_color)

    @Slot(QTreeWidgetItem, int)
    def _on_explorer_item_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        doc = item.data(0, Qt.ItemDataRole.UserRole)
        if doc and hasattr(doc, "content"):
            title = doc.title if hasattr(doc, "title") else "Document"
            # Prevent opening the same document twice
            if title in self.open_editors:
                self.source_panel.open_tab(title)
            else:
                self._open_document_tab(title, doc.content, doc)

    def _set_all_generation_states(self, is_generating: bool) -> None:
        for editor in self.open_editors.values():
            editor.set_generation_state(is_generating)

    @Slot()
    def _on_click_select_deck(self) -> None:
        dialog = DeckSelectionDialog(title="Sélectionner un paquet cible", items=self.decks_cache, parent=self)
        if dialog.exec():
            selected = dialog.get_selected_item()
            if selected:
                self._set_current_deck(selected)

    def _set_current_deck(self, deck: Any) -> None:
        self.current_deck = deck
        name = getattr(deck, "name", str(deck))
        self.btn_select_deck.setText(name)

    @Slot()
    def _on_click_select_model(self) -> None:
        dialog = SelectionDialog(title="Sélectionner un modèle de carte", items=self.models_cache, display_func=lambda m: m.name, parent=self)
        if dialog.exec():
            selected = dialog.get_selected_item()
            if selected:
                self._set_current_model(selected)

    def _set_current_model(self, model: Any) -> None:
        self.current_model = model
        name = getattr(model, "name", str(model))
        self.btn_select_model.setText(name)
        self._on_model_changed()

    @Slot()
    def _on_model_changed(self) -> None:
        selected_nt = self.current_model
        fields = ["Recto", "Verso", "Statut"]
        if selected_nt and isinstance(selected_nt, NoteTypeModel) and selected_nt.fields_schema:
            try:
                schema_fields = json.loads(str(selected_nt.fields_schema))
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

    @Slot(str)
    def _on_generate(self, text_source: str = "") -> None:
        if not text_source:
            show_toast(self, "Veuillez saisir un texte source ou sélectionner un document.", is_error=True)
            return

        selected_nt = self.current_model
        selected_pipeline = self.pipeline_combo.currentData()
        selected_engine = self.engine_combo.currentData()

        if not selected_engine:
            show_toast(self, "Aucun moteur IA configuré. Veuillez configurer les clés API dans les paramètres.", is_error=True)
            return

        nt_id = selected_nt.id if selected_nt and hasattr(selected_nt, "id") else 1
        nt_schema = str(selected_nt.fields_schema) if selected_nt and hasattr(selected_nt, "fields_schema") and selected_nt.fields_schema else '["Front", "Back"]'

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

        self._set_all_generation_states(True)

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
        self._set_all_generation_states(False)
        self.generated_cards = cards
        self.current_preview_index = 0

        self._populate_results_table()
        self._update_card_preview()
        show_toast(self, f"{len(cards)} cartes générées avec succès !")

    @Slot(str)
    def _on_worker_error(self, err_msg: str) -> None:
        self._set_all_generation_states(False)
        self.err_lbl.setText(f"⚠️ Erreur de génération : {err_msg}")
        self.results_panel.set_tab_title(1, "Journal des Erreurs (1)")
        show_toast(self, f"Erreur : {err_msg}", is_error=True)

    @Slot()
    def _on_worker_cancelled(self) -> None:
        self._set_all_generation_states(False)
        show_toast(self, "Génération annulée par l'utilisateur.")

    @Slot()
    def _on_cancel_generation(self) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.cancel()

    def _populate_results_table(self) -> None:
        self.results_table.blockSignals(True)
        self.results_table.setRowCount(len(self.generated_cards))
        self.results_panel.set_tab_title(0, f"Cartes Générées ({len(self.generated_cards)})")

        col_count = self.results_table.columnCount()

        for row, card in enumerate(self.generated_cards):
            card["status"] = card.get("status", "À valider")
            front_text = card.get("Front", card.get("Recto", ""))
            back_text = card.get("Back", card.get("Verso", ""))

            self.results_table.setItem(row, 0, QTableWidgetItem(front_text))

            badge_container = QWidget()
            badge_layout = QHBoxLayout(badge_container)
            badge_layout.setContentsMargins(8, 2, 8, 2)

            status_text = card["status"]
            variant = "warning" if status_text == "À valider" or status_text == "En attente" else "success"
            if status_text == "Rejetée":
                variant = "error"

            badge = Badge(status_text, variant=variant)
            badge_layout.addWidget(badge)
            badge_layout.addStretch()

            if col_count > 2:
                self.results_table.setItem(row, 1, QTableWidgetItem(back_text))
                self.results_table.setItem(row, col_count - 1, QTableWidgetItem())
                self.results_table.setCellWidget(row, col_count - 1, badge_container)
            else:
                self.results_table.setItem(row, 1, QTableWidgetItem())
                self.results_table.setCellWidget(row, 1, badge_container)

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
        selected_nt = self.current_model

        self.preview_widget.card_preview_widget.update_preview(
            note_type=selected_nt,
            fields_dict=card,
            override_templates=None,
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

        selected_nt = self.current_model
        if not selected_nt:
            show_toast(self, "Aucun type de note (modèle) sélectionné.", is_error=True)
            return

        deck_data = self.current_deck
        deck_name = deck_data.name if deck_data and hasattr(deck_data, "name") else "Général"

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

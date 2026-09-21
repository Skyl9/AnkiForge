from __future__ import annotations

import datetime
import json
import logging
import time
import uuid
from typing import Any

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSplitter,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    DocumentChunkModel,
    DocumentModel,
    LLMConfigModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionModel,
    PersonaModel,
    PipelineModel,
    PipelineStepModel,
    db,
)
from ankiforge.services.batch.models import BatchTaskSnapshot
from ankiforge.services.parsing.chunking_service import ChunkingService
from ankiforge.services.settings_service import SettingsService
from ankiforge.services.workers.batch_worker import BatchTaskPayload, BatchWorker
from ankiforge.ui.components import (
    Badge,
    EmptyStateWidget,
    IconButton,
    IdePanel,
    OptionToggleRow,
    PrimaryButton,
    SecondaryButton,
    StyledComboBox,
    StyledTableWidget,
    StyledTextEdit,
)
from ankiforge.ui.components.deck_select_window import DeckSelectWindow
from ankiforge.ui.components.document_picker_button import DocumentPickerButton
from ankiforge.ui.dialogs.selection_dialog import SelectionDialog
from ankiforge.ui.theme import DesignTokens, apply_shadow
from ankiforge.ui.views.batch_view.constants import apply_pill_style
from ankiforge.ui.views.batch_view.widgets import (
    CicdMetricCard,
    ProgressTableCellWidget,
)
from ankiforge.ui.widgets.segment_inspector_widget import SegmentInspectorWidget
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.anki_renderer import get_max_cloze_index
from ankiforge.utils.icon_loader import load_on_accent_icon, load_phosphor_icon
from ankiforge.utils.logger import log_and_notify_error
from ankiforge.utils.tags import build_document_tags

logger = logging.getLogger(__name__)


class BatchView(QWidget):
    """
    Batch Factory CI/CD View — 100% Conforme à la Maquette concept_ide/index.html (L1883-L2062).
    """

    def __init__(self, ai_manager: Any | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ai_manager = ai_manager
        self.worker: BatchWorker | None = None
        self.queue_tasks_data: list[dict[str, Any]] = []
        self._batch_scope_results: dict[int, dict[str, Any]] = {}
        self.cell_widgets_map: dict[int, ProgressTableCellWidget] = {}
        self.status_badges_map: dict[int, Badge] = {}
        self.cards_items_map: dict[int, QTableWidgetItem] = {}
        self._total_cards_accumulated = 0
        self.start_timestamp = 0.0
        self.current_deck: DeckModel | None = None
        self.current_model: NoteTypeModel | None = None
        self.decks_cache: list[DeckModel] = []
        self.models_cache: list[NoteTypeModel] = []
        self._deck_modal: DeckSelectWindow | None = None
        self._segment_inspector_doc: DocumentModel | None = None  # doc actuellement prévisualisé dans l'inspecteur

        self._setup_ui()
        self._connect_signals()
        self.refresh_data()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # TOP ROW: Metrics Cards
        metrics_container = QWidget()
        metrics_container.setObjectName("batchMetricsContainer")
        metrics_row = QHBoxLayout(metrics_container)
        metrics_row.setContentsMargins(12, 10, 12, 10)
        metrics_row.setSpacing(12)

        self.card_status = CicdMetricCard("STATUT GLOBAL", "En attente", "ph.check-circle", color=DesignTokens.COLOR_GREEN)
        self.card_time = CicdMetricCard("TEMPS RESTANT", "--:--:--", "ph.timer", color=DesignTokens.COLOR_BLUE)
        self.card_cards = CicdMetricCard("CARTES GÉNÉRÉES", "0 / 0", "ph.cards", color=DesignTokens.COLOR_PURPLE)
        self.card_cost = CicdMetricCard("COÛT ESTIMÉ", "$0.00", "ph.coin", color=DesignTokens.COLOR_YELLOW)

        metrics_row.addWidget(self.card_status, 1)
        metrics_row.addWidget(self.card_time, 1)
        metrics_row.addWidget(self.card_cards, 1)
        metrics_row.addWidget(self.card_cost, 1)

        main_layout.addWidget(metrics_container)

        # MAIN SPLITTER
        self.main_splitter = QSplitter(Qt.Orientation.Vertical)
        main_layout.addWidget(self.main_splitter, 1)

        # MIDDLE ROW
        self.middle_splitter = QSplitter(Qt.Orientation.Horizontal)

        # LEFT PANEL
        self.build_panel = IdePanel(detachable=True)
        self.build_panel.setMinimumWidth(320)
        self.build_panel.setMaximumWidth(380)

        build_content = QWidget()
        build_main_layout = QVBoxLayout(build_content)
        build_main_layout.setContentsMargins(0, 0, 0, 0)
        build_main_layout.setSpacing(0)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet("QScrollArea { background: transparent; border: none; } QWidget#scrollContent { background: transparent; border: none; }")

        scroll_content = QWidget()
        scroll_content.setObjectName("scrollContent")
        build_layout = QVBoxLayout(scroll_content)
        build_layout.setContentsMargins(8, 8, 8, 8)
        build_layout.setSpacing(8)

        scroll_area.setWidget(scroll_content)
        scroll_area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        scroll_area.setMinimumHeight(100)
        build_main_layout.addWidget(scroll_area, stretch=1)

        # Section 1: Source (Document Source - Miroir de CreationView)
        src_card = QFrame()
        src_card.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)
        src_layout = QVBoxLayout(src_card)
        src_layout.setContentsMargins(8, 8, 8, 8)
        src_layout.setSpacing(6)

        src_top = QHBoxLayout()
        src_top.setContentsMargins(0, 0, 0, 0)
        src_top.setSpacing(6)
        src_ico = QLabel()
        src_ico.setPixmap(load_phosphor_icon("ph.files", color=DesignTokens.COLOR_BLUE).pixmap(14, 14))
        src_ico.setStyleSheet("border: none; background: transparent;")
        self.lbl_src = QLabel("DOCUMENTS SOURCES")
        self.lbl_src.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-weight: 700; font-size: 11px; letter-spacing: 0.5px; border: none; background: transparent;")
        src_top.addWidget(src_ico)
        src_top.addWidget(self.lbl_src)
        src_top.addStretch()

        self.lbl_selected_docs_count = QLabel("0 sélectionné(s)")
        self.lbl_selected_docs_count.setStyleSheet(f"color: {DesignTokens.ACCENT_PRIMARY}; font-size: 10px; font-weight: bold; border: none; background: transparent;")
        src_top.addWidget(self.lbl_selected_docs_count)
        src_layout.addLayout(src_top)

        # Bouton-sélecteur modal interactif de documents (remplace l'ancienne liste)
        self.doc_picker_btn = DocumentPickerButton(self)
        self.doc_picker_btn.document_changed.connect(self._on_picker_document_changed)
        src_layout.addWidget(self.doc_picker_btn)

        # Bouton explicite pour ouvrir la modale de délimitation et découpage du document
        self.btn_delimit_doc = SecondaryButton("Délimiter & Découper le document...")
        self.btn_delimit_doc.setIcon(load_phosphor_icon("ph.crop", color=DesignTokens.TEXT_PRIMARY))
        self.btn_delimit_doc.setToolTip("Ouvrir l'outil visuel de délimitation et de découpage en sections du document")
        self.btn_delimit_doc.clicked.connect(self._on_open_delimitation_for_batch_doc)
        self.btn_delimit_doc.setVisible(False)
        src_layout.addWidget(self.btn_delimit_doc)

        # Inspecteur de découpage et de portée
        self.segment_inspector = SegmentInspectorWidget(parent=self)
        self.segment_inspector.setVisible(False)  # masqué jusqu'à sélection d'un doc
        src_layout.addWidget(self.segment_inspector)

        build_layout.addWidget(src_card)

        # Compatibilité ascendante : widgets conservés pour tests et rétro-compatibilité mais masqués
        self.doc_search_input = QLineEdit(self)
        self.doc_search_input.hide()
        self.doc_search_input.textChanged.connect(self._on_doc_search_changed)

        self.docs_list = QListWidget(self)
        self.docs_list.hide()
        self.docs_list.itemChanged.connect(self._on_doc_item_check_changed)

        self.btn_check_all_docs = SecondaryButton("Tout cocher")
        self.btn_check_all_docs.hide()
        self.btn_check_all_docs.clicked.connect(lambda: self._set_all_docs_checked(True))

        self.btn_uncheck_all_docs = SecondaryButton("Tout décocher")
        self.btn_uncheck_all_docs.hide()
        self.btn_uncheck_all_docs.clicked.connect(lambda: self._set_all_docs_checked(False))

        self.doc_combo = StyledComboBox(self)
        self.doc_combo.hide()

        # Section 2: Cibles Anki
        target_card = QFrame()
        target_card.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)
        target_layout = QVBoxLayout(target_card)
        target_layout.setContentsMargins(8, 8, 8, 8)
        target_layout.setSpacing(6)

        target_top = QHBoxLayout()
        target_top.setContentsMargins(0, 0, 0, 0)
        target_top.setSpacing(6)
        target_ico = QLabel()
        target_ico.setPixmap(load_phosphor_icon("ph.cards", color=DesignTokens.ACCENT_PRIMARY).pixmap(14, 14))
        target_ico.setStyleSheet("border: none; background: transparent;")
        lbl_target = QLabel("CIBLES ANKI")
        lbl_target.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-weight: 700; font-size: 11px; letter-spacing: 0.5px; border: none; background: transparent;")
        target_top.addWidget(target_ico)
        target_top.addWidget(lbl_target)
        target_top.addStretch()
        target_layout.addLayout(target_top)

        self.btn_select_deck = SecondaryButton("Sélectionner un paquet...")
        self.btn_select_deck.setIcon(load_phosphor_icon("ph.folder-open", color=DesignTokens.TEXT_MUTED))
        self.btn_select_deck.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_select_deck.setStyleSheet(
            f"text-align: left; padding: 6px 10px; border-radius: 6px; border: 1px solid {DesignTokens.BORDER_COLOR}; background: {DesignTokens.BG_PANEL}; font-weight: 500;"
        )
        target_layout.addWidget(self.btn_select_deck)

        self.btn_select_model = SecondaryButton("Sélectionner un modèle...")
        self.btn_select_model.setIcon(load_phosphor_icon("ph.file-code", color=DesignTokens.TEXT_MUTED))
        self.btn_select_model.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_select_model.setStyleSheet(
            f"text-align: left; padding: 6px 10px; border-radius: 6px; border: 1px solid {DesignTokens.BORDER_COLOR}; background: {DesignTokens.BG_PANEL}; font-weight: 500;"
        )
        target_layout.addWidget(self.btn_select_model)
        build_layout.addWidget(target_card)

        # Section 3: Orchestration IA
        ai_card = QFrame()
        ai_card.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)
        ai_layout = QVBoxLayout(ai_card)
        ai_layout.setContentsMargins(8, 8, 8, 8)
        ai_layout.setSpacing(6)

        ai_top = QHBoxLayout()
        ai_top.setContentsMargins(0, 0, 0, 0)
        ai_top.setSpacing(6)
        ai_ico = QLabel()
        ai_ico.setPixmap(load_phosphor_icon("ph.lightning", color=DesignTokens.COLOR_YELLOW).pixmap(14, 14))
        ai_ico.setStyleSheet("border: none; background: transparent;")
        lbl_ai = QLabel("ORCHESTRATION IA")
        lbl_ai.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-weight: 700; font-size: 11px; letter-spacing: 0.5px; border: none; background: transparent;")
        ai_top.addWidget(ai_ico)
        ai_top.addWidget(lbl_ai)
        ai_top.addStretch()
        ai_layout.addLayout(ai_top)

        self.engine_combo = StyledComboBox()
        self.engine_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.engine_combo.setMinimumContentsLength(8)
        self.engine_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.engine_combo.currentIndexChanged.connect(self._on_engine_changed)
        ai_layout.addWidget(self.engine_combo)

        self.btn_no_engine_help = SecondaryButton("Configurer les Moteurs IA")
        self.btn_no_engine_help.setIcon(load_phosphor_icon("ph.gear", color=DesignTokens.COLOR_YELLOW))
        self.btn_no_engine_help.setStyleSheet(f"color: {DesignTokens.COLOR_YELLOW}; border: 1px solid {DesignTokens.COLOR_YELLOW}; font-size: 11px;")
        self.btn_no_engine_help.hide()
        ai_layout.addWidget(self.btn_no_engine_help)

        self.pipeline_combo = StyledComboBox()
        self.pipeline_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.pipeline_combo.setMinimumContentsLength(8)
        self.pipeline_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.pipeline_combo.currentIndexChanged.connect(self._on_pipeline_changed)
        ai_layout.addWidget(self.pipeline_combo)

        self.btn_no_pipeline_help = SecondaryButton("Créer un Pipeline d'Agents")
        self.btn_no_pipeline_help.setIcon(load_phosphor_icon("ph.plus", color=DesignTokens.ACCENT_PRIMARY))
        self.btn_no_pipeline_help.setStyleSheet(f"color: {DesignTokens.ACCENT_PRIMARY}; border: 1px solid {DesignTokens.ACCENT_PRIMARY}; font-size: 11px;")
        self.btn_no_pipeline_help.hide()
        ai_layout.addWidget(self.btn_no_pipeline_help)

        opt_layout = QHBoxLayout()
        opt_layout.setContentsMargins(0, 4, 0, 0)
        opt_layout.setSpacing(6)

        saved_vision = SettingsService.get("batch/use_vision", True)
        self.cb_vision = OptionToggleRow("Vision (PDF)", icon_name="ph.eye", checked=bool(saved_vision))
        self.cb_vision.toggled.connect(lambda s: SettingsService.set("batch/use_vision", s, category="batch"))

        saved_autoval = SettingsService.get("batch/auto_validation", True)
        self.cb_autoval = OptionToggleRow("Validation auto", icon_name="ph.shield-check", checked=bool(saved_autoval))
        self.cb_autoval.toggled.connect(lambda s: SettingsService.set("batch/auto_validation", s, category="batch"))

        saved_full_document = SettingsService.get("batch/process_full_document", False)
        self.cb_full_document = OptionToggleRow("Document complet par chunks", icon_name="ph.files", checked=bool(saved_full_document))
        self.cb_full_document.hide()

        opt_layout.addWidget(self.cb_vision, 1)
        opt_layout.addWidget(self.cb_autoval, 1)
        ai_layout.addLayout(opt_layout)

        build_layout.addWidget(ai_card)

        # Section 4: Paramètres Avancés
        self.btn_toggle_advanced = QPushButton()
        self.btn_toggle_advanced.setStyleSheet("background: transparent; border: none; text-align: left; padding: 4px 0;")
        self.btn_toggle_advanced.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_advanced.setToolTip("Déplier / replier les options avancées de découpage et vision")

        advanced_header = QHBoxLayout(self.btn_toggle_advanced)
        advanced_header.setContentsMargins(0, 0, 0, 0)
        self.adv_lbl = QLabel("Paramètres Avancés")
        self.adv_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11px; font-weight: 500; background: transparent; border: none;")

        self.advanced_icon = QLabel()
        self.advanced_icon.setPixmap(load_phosphor_icon("ph.caret-right", color=DesignTokens.TEXT_MUTED).pixmap(12, 12))
        self.advanced_icon.setStyleSheet("background: transparent; border: none;")

        advanced_header.addWidget(self.adv_lbl)
        advanced_header.addStretch()
        advanced_header.addWidget(self.advanced_icon)
        build_layout.addWidget(self.btn_toggle_advanced)

        self.advanced_container = QFrame()
        self.advanced_container.setObjectName("batchAdvancedContainer")
        self.advanced_container.setVisible(False)
        self.advanced_container.setStyleSheet(f"""
            QFrame#batchAdvancedContainer {{
                background: {DesignTokens.BG_PANEL};
                padding: 8px;
                border-radius: 4px;
                border: 1px solid {DesignTokens.BORDER_COLOR};
            }}
        """)
        advanced_layout = QVBoxLayout(self.advanced_container)
        advanced_layout.setContentsMargins(0, 0, 0, 0)
        advanced_layout.setSpacing(8)

        temp_layout = QVBoxLayout()
        temp_header = QHBoxLayout()
        self.temp_lbl = QLabel("Température")
        self.temp_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px; border: none; background: transparent;")
        saved_temp = float(SettingsService.get("batch/temperature", 0.7))
        self.val_temp_lbl = QLabel(f"{saved_temp:.1f}")
        self.val_temp_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-family: {DesignTokens.FONT_CODE}; font-size: 11px; border: none; background: transparent;")
        temp_header.addWidget(self.temp_lbl)
        temp_header.addStretch()
        temp_header.addWidget(self.val_temp_lbl)

        self.slider_temp = QSlider(Qt.Orientation.Horizontal)
        self.slider_temp.setMinimum(0)
        self.slider_temp.setMaximum(10)
        self.slider_temp.setValue(int(round(saved_temp * 10)))
        self.slider_temp.valueChanged.connect(self._on_temp_slider_changed)

        temp_layout.addLayout(temp_header)
        temp_layout.addWidget(self.slider_temp)
        advanced_layout.addLayout(temp_layout)

        tokens_layout = QVBoxLayout()
        tokens_header = QHBoxLayout()
        self.tokens_lbl = QLabel("Max Tokens")
        self.tokens_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px; border: none; background: transparent;")
        saved_tokens = int(SettingsService.get("batch/max_tokens", 65536))
        tokens_step = max(1, min(64, round(saved_tokens / 1024)))
        self.val_tokens_lbl = QLabel(f"{tokens_step * 1024:,} tks".replace(",", " "))
        self.val_tokens_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-family: {DesignTokens.FONT_CODE}; font-size: 11px; border: none; background: transparent;")
        tokens_header.addWidget(self.tokens_lbl)
        tokens_header.addStretch()
        tokens_header.addWidget(self.val_tokens_lbl)

        self.slider_tokens = QSlider(Qt.Orientation.Horizontal)
        self.slider_tokens.setMinimum(1)
        self.slider_tokens.setMaximum(64)
        self.slider_tokens.setValue(tokens_step)
        self.slider_tokens.valueChanged.connect(self._on_tokens_slider_changed)

        tokens_layout.addLayout(tokens_header)
        tokens_layout.addWidget(self.slider_tokens)
        advanced_layout.addLayout(tokens_layout)

        build_layout.addWidget(self.advanced_container)
        build_layout.addStretch()

        self.btn_add_to_queue = PrimaryButton("Ajouter à la Queue", tooltip="Ajouter la sélection actuelle à la file d'attente du lot")
        self.btn_add_to_queue.setIcon(load_on_accent_icon("ph.plus"))
        apply_shadow(self.btn_add_to_queue, blur=10, offset_y=2, color=DesignTokens.ACCENT_GLOW)
        self.btn_add_to_queue.clicked.connect(self._on_add_to_queue_clicked)

        btn_container = QWidget()
        btn_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        btn_layout = QVBoxLayout(btn_container)
        btn_layout.setContentsMargins(10, 6, 10, 8)
        btn_layout.addWidget(self.btn_add_to_queue)
        build_main_layout.addWidget(btn_container, stretch=0)

        self.build_panel.setMinimumWidth(380)
        self.build_panel.add_tab("Paramètres du Build", build_content, "ph.sliders-horizontal", closable=False)
        self.middle_splitter.addWidget(self.build_panel)

        # RIGHT PANEL
        self.queue_panel = IdePanel(detachable=True)

        self.btn_clear_table = IconButton("ph.trash", tooltip="Vider la file d'attente", size=22)
        self.btn_clear_table.clicked.connect(self._on_clear_queue)
        self.queue_panel.add_header_widget(self.btn_clear_table)

        self.btn_start_pipeline = PrimaryButton("Démarrer Pipeline", tooltip="Démarrer l'exécution du traitement par lots en arrière-plan")
        self.btn_start_pipeline.setIcon(load_on_accent_icon("ph.play"))
        self.btn_start_pipeline.setStyleSheet(f"""
            QPushButton {{
                background-color: {DesignTokens.COLOR_GREEN};
                border: 1px solid {DesignTokens.COLOR_GREEN};
                color: {DesignTokens.TEXT_ON_ACCENT};
                font-weight: bold;
                padding: 6px 18px;
                border-radius: 6px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: {DesignTokens.COLOR_GREEN_TEXT};
                border-color: {DesignTokens.COLOR_GREEN_TEXT};
            }}
        """)
        apply_shadow(self.btn_start_pipeline, blur=16, offset_y=0, color="rgba(16, 185, 129, 0.45)")
        self.btn_start_pipeline.clicked.connect(self._on_start_batch)
        self.queue_panel.add_header_widget(self.btn_start_pipeline)

        queue_content = QWidget()
        queue_layout = QVBoxLayout(queue_content)
        queue_layout.setContentsMargins(0, 0, 0, 0)
        queue_layout.setSpacing(0)

        self.queue_table = StyledTableWidget(["", "STATUT", "FICHIER / SOURCE", "PAQUET", "MODÈLE", "PIPELINE", "PROGRÈS", "CARTES", "ACTIONS"])
        self.queue_table.setSelectionBehavior(StyledTableWidget.SelectionBehavior.SelectRows)
        self.queue_table.verticalHeader().setDefaultSectionSize(46)

        header = self.queue_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(8, QHeaderView.ResizeMode.Fixed)

        self.queue_table.setColumnWidth(0, 32)
        self.queue_table.setColumnWidth(1, 100)
        self.queue_table.setColumnWidth(3, 110)
        self.queue_table.setColumnWidth(4, 110)
        self.queue_table.setColumnWidth(5, 120)
        self.queue_table.setColumnWidth(6, 150)
        self.queue_table.setColumnWidth(7, 80)
        self.queue_table.setColumnWidth(8, 50)

        self.queue_table.setStyleSheet(
            self.queue_table.styleSheet()
            + """
            QHeaderView::section {
                padding: 6px 8px;
                font-size: 11px;
            }
            QTableWidget::item {
                padding: 4px 6px;
            }
        """
        )

        queue_layout.addWidget(self.queue_table, 1)

        self.queue_empty = EmptyStateWidget(
            icon_name="ph.tray",
            title="File d'attente vide",
            description="Sélectionnez des documents et configurez la forge à gauche pour ajouter des tâches par lots.",
        )
        queue_layout.addWidget(self.queue_empty, 1)

        self.queue_panel.add_tab("File d'attente détaillée", queue_content, "ph.list-dashes", closable=False)
        self.middle_splitter.addWidget(self.queue_panel)

        self.middle_splitter.setSizes([400, 700])
        self.main_splitter.addWidget(self.middle_splitter)

        # BOTTOM ROW
        self.terminal_panel = IdePanel(detachable=True)
        self._terminal_expanded = True
        self._terminal_last_height = 240

        self.btn_toggle_terminal = IconButton("ph.caret-down", tooltip="Réduire / Déplier le terminal", size=20)
        self.btn_toggle_terminal.clicked.connect(self._toggle_terminal)
        self.terminal_panel.add_header_widget(self.btn_toggle_terminal)

        self.btn_clear_terminal = IconButton("ph.trash", tooltip="Effacer les logs du terminal", size=20)
        self.btn_clear_terminal.clicked.connect(self._on_clear_terminal_clicked)
        self.terminal_panel.add_header_widget(self.btn_clear_terminal)

        self.btn_scroll_lock = IconButton("ph.lock-key", tooltip="Verrouiller le défilement", size=20)
        self.btn_scroll_lock.clicked.connect(lambda: show_toast(self, "Verrouillage du défilement activé."))
        self.terminal_panel.add_header_widget(self.btn_scroll_lock)

        self.terminal_content = QWidget()
        terminal_layout = QVBoxLayout(self.terminal_content)
        terminal_layout.setContentsMargins(0, 0, 0, 0)
        terminal_layout.setSpacing(0)

        self.console_output = StyledTextEdit()
        self.console_output.setReadOnly(True)
        self.console_output.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {DesignTokens.BG_INPUT};
                color: {DesignTokens.COLOR_GREEN};
                font-family: '{DesignTokens.FONT_CODE}';
                font-size: 12px;
                line-height: 1.6;
                padding: 14px;
                border: none;
                selection-background-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        terminal_layout.addWidget(self.console_output, 1)

        self.terminal_panel.add_tab("root@ankiforge:~/pipeline_logs", self.terminal_content, "ph.terminal-window", closable=False)
        self.main_splitter.addWidget(self.terminal_panel)

        self.middle_splitter.setCollapsible(0, False)
        self.middle_splitter.setCollapsible(1, False)
        self.middle_splitter.setStretchFactor(0, 0)
        self.middle_splitter.setStretchFactor(1, 1)

        self.main_splitter.setCollapsible(0, False)
        self.main_splitter.setCollapsible(1, False)
        self.main_splitter.setStretchFactor(0, 3)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setSizes([500, 180])

        self._log_formatted_line("INFO", "Pipeline worker initialized.")
        self._update_queue_table()

    def _toggle_terminal(self) -> None:
        self._terminal_expanded = not self._terminal_expanded
        if self._terminal_expanded:
            self.terminal_content.setVisible(True)
            self.btn_toggle_terminal.setIcon(load_phosphor_icon("ph.caret-down", color=DesignTokens.TEXT_SECONDARY))
            self.main_splitter.setSizes([500, self._terminal_last_height])
        else:
            sizes = self.main_splitter.sizes()
            if len(sizes) > 1 and sizes[1] > 50:
                self._terminal_last_height = sizes[1]
            self.terminal_content.setVisible(False)
            self.btn_toggle_terminal.setIcon(load_phosphor_icon("ph.caret-up", color=DesignTokens.TEXT_SECONDARY))
            self.main_splitter.setSizes([800, 36])

    def _connect_signals(self) -> None:
        self.btn_select_deck.clicked.connect(self._on_click_select_deck)
        self.btn_select_model.clicked.connect(self._on_click_select_model)
        self.btn_toggle_advanced.clicked.connect(self._toggle_advanced_settings)
        self.btn_no_engine_help.clicked.connect(self._open_settings_modal)
        self.btn_no_pipeline_help.clicked.connect(lambda: show_toast(self, "Créez un pipeline dans l'onglet Pipelines."))
        self.docs_list.itemClicked.connect(self._on_doc_item_clicked)
        self.docs_list.itemDoubleClicked.connect(self._on_doc_item_double_clicked)
        self.segment_inspector.open_delimitation_requested.connect(self._on_open_delimitation_for_batch_doc)
        self.segment_inspector.open_scope_dialog_requested.connect(self._on_open_scope_dialog_for_batch_doc)

    @Slot(object)
    def _on_picker_document_changed(self, doc: DocumentModel | None) -> None:
        self._segment_inspector_doc = doc
        if doc is not None:
            self.btn_delimit_doc.setVisible(True)
            self.segment_inspector.setVisible(True)
            self.segment_inspector.set_document(doc)
            self.docs_list.blockSignals(True)
            for i in range(self.docs_list.count()):
                it = self.docs_list.item(i)
                d = it.data(Qt.ItemDataRole.UserRole)
                if d and getattr(d, "id", None) == doc.id:
                    it.setCheckState(Qt.CheckState.Checked)
                else:
                    it.setCheckState(Qt.CheckState.Unchecked)
            self.docs_list.blockSignals(False)
        else:
            self.btn_delimit_doc.setVisible(False)
            self.segment_inspector.setVisible(False)
            self.segment_inspector.set_document(None)
            self._set_all_docs_checked(False)
        self._update_selected_docs_count()

    @Slot(QListWidgetItem)
    def _on_doc_item_clicked(self, item: QListWidgetItem) -> None:
        doc = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(doc, DocumentModel):
            self._segment_inspector_doc = doc
            self.doc_picker_btn.set_document(doc, emit_signal=False)
            self.btn_delimit_doc.setVisible(True)
            self.segment_inspector.setVisible(True)
            self.segment_inspector.set_document(doc)
            self._update_selected_docs_count()

    @Slot(QListWidgetItem)
    def _on_doc_item_double_clicked(self, item: QListWidgetItem) -> None:
        if item.flags() & Qt.ItemFlag.ItemIsUserCheckable:
            new_state = Qt.CheckState.Unchecked if item.checkState() == Qt.CheckState.Checked else Qt.CheckState.Checked
            item.setCheckState(new_state)
        self._on_doc_item_clicked(item)

    @Slot()
    def _on_open_delimitation_for_batch_doc(self) -> None:
        doc = self._segment_inspector_doc or self.doc_picker_btn.get_document()
        if not doc:
            show_toast(self, "Veuillez sélectionner un document à délimiter.", is_error=True)
            return
        if getattr(doc, "id", None):
            try:
                doc = DocumentModel.get_by_id(doc.id)
            except Exception as err:
                logger.debug("Rechargement du document batch ignoré : %s", err)
        from ankiforge.ui.views.documents_view.dialogs.delimitation_dialog import DocumentDelimitationDialog

        dlg = DocumentDelimitationDialog(doc, context="batch", parent=self)
        if dlg.exec():
            reloaded_doc = DocumentModel.get_by_id(doc.id) if getattr(doc, "id", None) else doc
            self._segment_inspector_doc = reloaded_doc
            self.doc_picker_btn.set_document(reloaded_doc, emit_signal=False)
            sp = getattr(reloaded_doc, "start_page", 1) or 1
            ep = getattr(reloaded_doc, "end_page", None)
            if ep is not None:
                self.segment_inspector.input_page_scope.setText(f"{sp}-{ep}")
            self.segment_inspector.set_document(reloaded_doc)
            recomputed_chunks = self._resolve_batch_chunks(reloaded_doc)
            if recomputed_chunks:
                self.segment_inspector._chunks = recomputed_chunks
                self.segment_inspector._refresh_list_ui()
            self._update_selected_docs_count()
            chunks_count = len(recomputed_chunks)
            msg = f"Découpage validé : {chunks_count} section(s) prête(s) pour le lot !" if chunks_count > 0 else "Délimitation enregistrée pour le document."
            show_toast(self, msg)

    @Slot()
    def _on_open_scope_dialog_for_batch_doc(self) -> None:
        doc = self._segment_inspector_doc or self.doc_picker_btn.get_document()
        if not doc:
            show_toast(self, "Veuillez sélectionner un document pour définir sa portée.", is_error=True)
            return
        if getattr(doc, "id", None):
            try:
                doc = DocumentModel.get_by_id(doc.id)
            except Exception as err:
                logger.debug("Rechargement du document de portée ignoré : %s", err)
            self._segment_inspector_doc = doc
        from ankiforge.ui.dialogs.document_scope_dialog import DocumentScopeDialog

        initial_scope = self.segment_inspector.input_page_scope.text().strip()
        last_scope_result = self._batch_scope_results.get(int(doc.id)) if getattr(doc, "id", None) else None
        dlg = DocumentScopeDialog(doc, initial_scope_str=initial_scope, initial_scope_result=last_scope_result, parent=self)
        if dlg.exec():
            res = dlg.get_result()
            self._batch_scope_results[int(doc.id)] = res
            self.segment_inspector.apply_scope_result(res)
            self._update_selected_docs_count()

    def _on_doc_search_changed(self, text: str) -> None:
        query = text.strip().lower()
        for i in range(self.docs_list.count()):
            item = self.docs_list.item(i)
            doc_obj = item.data(Qt.ItemDataRole.UserRole)
            title = doc_obj.title.lower() if doc_obj else item.text().lower()
            item.setHidden(bool(query and query not in title))

    def _on_doc_item_check_changed(self, item: QListWidgetItem) -> None:
        self._update_selected_docs_count()

    def _set_all_docs_checked(self, checked: bool) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        self.docs_list.blockSignals(True)
        for i in range(self.docs_list.count()):
            it = self.docs_list.item(i)
            if not it.isHidden():
                it.setCheckState(state)
        self.docs_list.blockSignals(False)
        self._update_selected_docs_count()

    def _update_selected_docs_count(self) -> None:
        count = sum(1 for i in range(self.docs_list.count()) if self.docs_list.item(i).checkState() == Qt.CheckState.Checked)
        if count == 0 and hasattr(self, "doc_picker_btn") and self.doc_picker_btn.get_document():
            count = 1
        if hasattr(self, "lbl_selected_docs_count"):
            self.lbl_selected_docs_count.setText(f"{count} sélectionné(s)")
        if hasattr(self, "btn_add_to_queue"):
            self.btn_add_to_queue.setText(f"Ajouter à la Queue ({count})" if count > 0 else "Ajouter à la Queue")

    def refresh_data(self) -> None:
        try:
            self.doc_combo.blockSignals(True)
            self.doc_combo.clear()
            self.docs_list.blockSignals(True)
            self.docs_list.clear()
            docs = list(DocumentModel.select().order_by(DocumentModel.id.desc()))
            if docs:
                for doc in docs:
                    content = getattr(doc, "content", "") or ""
                    words = len(content.split())
                    ftype = (getattr(doc, "file_type", "") or "doc").lower()

                    icon_name = "ph.file-text"
                    icon_color = DesignTokens.COLOR_BLUE
                    if ftype == "pdf":
                        icon_name = "ph.file-pdf"
                        icon_color = DesignTokens.COLOR_RED
                    elif ftype in ("md", "markdown"):
                        icon_name = "ph.file-code"
                        icon_color = DesignTokens.COLOR_YELLOW
                    elif ftype == "album":
                        icon_name = "ph.images"
                        icon_color = DesignTokens.COLOR_PURPLE
                    elif ftype == "epub":
                        icon_name = "ph.book-open"
                        icon_color = DesignTokens.COLOR_PURPLE
                    elif ftype == "pptx":
                        icon_name = "ph.presentation"
                        icon_color = DesignTokens.COLOR_YELLOW
                    elif ftype in ("audio", "mp3", "m4a", "wav"):
                        icon_name = "ph.headphones"
                        icon_color = DesignTokens.COLOR_GREEN
                    elif ftype in ("youtube", "video"):
                        icon_name = "ph.youtube-logo"
                        icon_color = DesignTokens.COLOR_RED
                    elif ftype == "web":
                        icon_name = "ph.globe"
                        icon_color = DesignTokens.ACCENT_PRIMARY

                    self.doc_combo.addItem(load_phosphor_icon(icon_name, color=icon_color), doc.title, userData=doc)
                    it = QListWidgetItem(f"{doc.title} ({words} mots • {ftype.upper()})")
                    it.setIcon(load_phosphor_icon(icon_name, color=icon_color))
                    it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    it.setCheckState(Qt.CheckState.Unchecked)
                    it.setData(Qt.ItemDataRole.UserRole, doc)
                    self.docs_list.addItem(it)
            else:
                self.doc_combo.addItem("Aucun document disponible")
                empty_it = QListWidgetItem("Aucun document disponible dans la bibliothèque")
                empty_it.setFlags(Qt.ItemFlag.NoItemFlags)
                empty_it.setForeground(QColor(DesignTokens.TEXT_MUTED))
                self.docs_list.addItem(empty_it)
            self.doc_combo.blockSignals(False)
            self.docs_list.blockSignals(False)
            self._update_selected_docs_count()

            # Resynchroniser le segment inspector et doc_picker_btn si le doc inspecté est toujours valide
            if self._segment_inspector_doc:
                still_exists = any(getattr(d, "id", None) == self._segment_inspector_doc.id for d in docs)
                if still_exists:
                    self.doc_picker_btn.set_document(self._segment_inspector_doc, emit_signal=False)
                    self.segment_inspector.set_document(self._segment_inspector_doc)
                else:
                    self._segment_inspector_doc = None
                    self.doc_picker_btn.set_document(None, emit_signal=False)
                    self.segment_inspector.setVisible(False)

            decks = list(DeckModel.select())
            if not decks:
                DeckModel.get_or_create(name="Général")
                decks = list(DeckModel.select())
            self.decks_cache = decks
            if self.current_deck is None and self.decks_cache:
                self._set_current_deck(self.decks_cache[0])

            note_types = list(NoteTypeModel.select())
            self.models_cache = note_types
            if self.current_model is None and self.models_cache:
                self._set_current_model(self.models_cache[0])

            self.engine_combo.blockSignals(True)
            self.engine_combo.clear()
            engines = list(LLMConfigModel.select().order_by(LLMConfigModel.sort_order.asc(), LLMConfigModel.id.asc()))
            if not engines:
                with db.atomic():
                    LLMConfigModel.create(
                        display_name="Google Gemini 3.5 Flash Lite",
                        provider="gemini",
                        model_id="gemini-3.5-flash-lite",
                        context_limit=1048576,
                        max_tokens=65536,
                        sort_order=0,
                        is_free=True,
                    )
                    LLMConfigModel.create(
                        display_name="GPT-4o",
                        provider="openai",
                        model_id="gpt-4o",
                        context_limit=128000,
                        max_tokens=16384,
                        sort_order=10,
                    )
                    LLMConfigModel.create(
                        display_name="Claude 3.5 Sonnet",
                        provider="anthropic",
                        model_id="claude-3-5-sonnet-20240620",
                        context_limit=200000,
                        max_tokens=8192,
                        sort_order=20,
                    )
                engines = list(LLMConfigModel.select().order_by(LLMConfigModel.sort_order.asc(), LLMConfigModel.id.asc()))
            if engines:
                for eg in engines:
                    display_name = getattr(eg, "display_name", getattr(eg, "name", str(eg)))
                    self.engine_combo.addItem(load_phosphor_icon("ph.cpu", color=DesignTokens.ACCENT_PRIMARY), display_name, userData=eg)
                self.btn_no_engine_help.hide()
                saved_engine_id = SettingsService.get("batch/engine_id")
                if saved_engine_id is not None:
                    for idx in range(self.engine_combo.count()):
                        item_eg = self.engine_combo.itemData(idx)
                        if item_eg and getattr(item_eg, "id", None) == saved_engine_id:
                            self.engine_combo.setCurrentIndex(idx)
                            break
            else:
                self.btn_no_engine_help.show()
            self.engine_combo.blockSignals(False)
            self._on_engine_changed()

            self.pipeline_combo.blockSignals(True)
            self.pipeline_combo.clear()
            pipelines = list(PipelineModel.select())
            if not pipelines:
                pipe = PipelineModel.create(name="Excellence (Standard)", description="Génération structurée de cartes mémoires")
                persona = PersonaModel.select().first()
                PipelineStepModel.create(
                    pipeline=pipe,
                    persona=persona,
                    step_type="LLM_PROMPT",
                    step_order=1,
                    config_data=json.dumps(
                        {
                            "prompt_template": (
                                "Tu es un expert pédagogique de création de cartes Anki.\n"
                                "Analyse le texte suivant et génère des cartes mémoire de haute qualité atomiques.\n\n"
                                "TEXTE SOURCE :\n{{ text_source }}\n\n"
                                "MODÈLE CIBLE : {{ note_type }}\n"
                                "CHAMPS REQUIS : {{ fields_str }}\n\n"
                                "Génère ta réponse au format JSON contenant un tableau de cartes sous la clé 'notes' ou directement un tableau d'objets."
                            ),
                            "output_format": "json",
                        }
                    ),
                )
                pipelines = list(PipelineModel.select())
            if pipelines:
                for pipe in pipelines:
                    step_cnt = PipelineStepModel.select().where(PipelineStepModel.pipeline == pipe).count()
                    display_txt = f"{pipe.name} ({step_cnt} étapes)" if step_cnt > 0 else pipe.name
                    self.pipeline_combo.addItem(load_phosphor_icon("ph.tree-structure", color=DesignTokens.COLOR_BLUE), display_txt, userData=pipe)
                self.btn_no_pipeline_help.hide()
                saved_pipe_id = SettingsService.get("batch/pipeline_id")
                if saved_pipe_id is not None:
                    for idx in range(self.pipeline_combo.count()):
                        item_pipe = self.pipeline_combo.itemData(idx)
                        if item_pipe and getattr(item_pipe, "id", None) == saved_pipe_id:
                            self.pipeline_combo.setCurrentIndex(idx)
                            break
            else:
                self.btn_no_pipeline_help.show()
            self.pipeline_combo.blockSignals(False)

        except Exception as e:
            logger.warning("Erreur refresh_data batch_view: %s", e)

    def _on_temp_slider_changed(self, v: int) -> None:
        self.val_temp_lbl.setText(f"{v / 10:.1f}")
        SettingsService.set("batch/temperature", round(v / 10.0, 1), category="batch")

    def _on_tokens_slider_changed(self, v: int) -> None:
        tokens_val = v * 1024
        self.val_tokens_lbl.setText(f"{tokens_val:,} tks".replace(",", " "))
        SettingsService.set("batch/max_tokens", tokens_val, category="batch")

    @Slot()
    def _on_pipeline_changed(self) -> None:
        pipe = self.pipeline_combo.currentData()
        if pipe and hasattr(pipe, "id"):
            SettingsService.set("batch/pipeline_id", pipe.id, category="batch")

    @Slot()
    def _on_engine_changed(self) -> None:
        eg = self.engine_combo.currentData()
        if eg and hasattr(eg, "id"):
            SettingsService.set("batch/engine_id", eg.id, category="batch")
        if eg and hasattr(self, "slider_tokens"):
            max_t = int(getattr(eg, "max_tokens", 16384) or 16384)
            saved_tokens = SettingsService.get("batch/max_tokens")
            step_val = max(1, min(64, round(int(saved_tokens) / 1024))) if saved_tokens is not None else max(1, min(64, round(max_t / 1024)))
            self.slider_tokens.blockSignals(True)
            self.slider_tokens.setValue(step_val)
            self.slider_tokens.blockSignals(False)
            self.val_tokens_lbl.setText(f"{step_val * 1024:,} tks".replace(",", " "))

    def is_dirty(self) -> bool:
        return len(self.queue_tasks_data) > 0

    @Slot()
    def _on_click_select_deck(self) -> None:
        try:
            if self._deck_modal and self._deck_modal.isVisible():
                self._deck_modal.raise_()
                self._deck_modal.activateWindow()
                return
        except RuntimeError:
            self._deck_modal = None
        self._deck_modal = DeckSelectWindow(title="Sélectionner un paquet cible", parent=self)
        self._deck_modal.deck_selected.connect(self._on_deck_selected)
        self._deck_modal.show()

    @Slot(int, str)
    def _on_deck_selected(self, deck_id: int, deck_name: str) -> None:
        try:
            deck = DeckModel.get_by_id(deck_id)
            self._set_current_deck(deck)
        except Exception as e:
            logger.error("Impossible de trouver le paquet %s : %s", deck_name, e)

    def _set_current_deck(self, deck: Any) -> None:
        self.current_deck = deck
        name = getattr(deck, "name", str(deck))
        self.btn_select_deck.setText(name)

    @Slot()
    def _on_click_select_model(self) -> None:
        dialog = SelectionDialog(
            title="Sélectionner un modèle de carte",
            items=self.models_cache,
            display_func=lambda m: m.name,
            parent=self,
        )
        if dialog.exec():
            selected = dialog.get_selected_item()
            if selected:
                self._set_current_model(selected)

    def _set_current_model(self, model: Any) -> None:
        self.current_model = model
        name = getattr(model, "name", str(model))
        self.btn_select_model.setText(name)

    @Slot()
    def _toggle_advanced_settings(self) -> None:
        is_visible = not self.advanced_container.isVisible()
        self.advanced_container.setVisible(is_visible)
        icon_name = "ph.caret-down" if is_visible else "ph.caret-right"
        self.advanced_icon.setPixmap(load_phosphor_icon(icon_name, color=DesignTokens.TEXT_MUTED).pixmap(14, 14))

    @Slot()
    def _open_settings_modal(self) -> None:
        from ankiforge.ui.widgets.settings_modal import SettingsModal

        modal = SettingsModal(ai_manager=self.ai_manager, parent=self)
        modal.exec()

    def _log_formatted_line(self, level: str, msg: str) -> None:
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        level_color = DesignTokens.COLOR_BLUE
        if level == "WARN":
            level_color = DesignTokens.COLOR_YELLOW
        elif level == "SUCCESS":
            level_color = DesignTokens.COLOR_GREEN
        elif level == "ERROR":
            level_color = DesignTokens.COLOR_RED

        formatted_html = f"<span style='color: {DesignTokens.TEXT_MUTED}'>[{now_str}]</span> <span style='color: {level_color}; font-weight: bold;'>{level}</span> {msg}"
        self.console_output.appendHtml(formatted_html)

    @Slot()
    def _on_clear_terminal_clicked(self) -> None:
        self.console_output.clear()
        self._log_formatted_line("INFO", "Terminal logs cleared.")

    @Slot()
    def _on_browse_local_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(self, "Sélectionner un document source", "", "Documents (*.pdf *.txt *.md *.docx *.ipynb *.py);;Tous (*)")
        if file_path:
            import os

            title = os.path.basename(file_path)
            _, ext = os.path.splitext(title)
            clean_ext = ext.lstrip(".").lower() or "md"
            doc, _ = DocumentModel.get_or_create(title=title, defaults={"file_type": clean_ext, "content": f"Contenu du fichier {title}"})
            self.refresh_data()
            show_toast(self, f"Document '{title}' chargé !")

    @Slot()
    def _on_add_to_queue_clicked(self) -> None:
        checked_docs: list[DocumentModel] = []
        picker_doc = self.doc_picker_btn.get_document()
        if picker_doc:
            checked_docs.append(picker_doc)
        else:
            for i in range(self.docs_list.count()):
                it = self.docs_list.item(i)
                if it.checkState() == Qt.CheckState.Checked:
                    doc_obj = it.data(Qt.ItemDataRole.UserRole)
                    if isinstance(doc_obj, DocumentModel):
                        checked_docs.append(doc_obj)

            # Si aucun document coché, fallback sur le doc inspecté, l'élément courant ou le combo
            if not checked_docs and self._segment_inspector_doc:
                checked_docs.append(self._segment_inspector_doc)
            elif not checked_docs and self.docs_list.currentItem():
                cur_doc = self.docs_list.currentItem().data(Qt.ItemDataRole.UserRole)
                if isinstance(cur_doc, DocumentModel):
                    checked_docs.append(cur_doc)
            elif not checked_docs and hasattr(self, "doc_combo") and self.doc_combo.currentData():
                single_doc = self.doc_combo.currentData()
                if isinstance(single_doc, DocumentModel):
                    checked_docs.append(single_doc)

        if not checked_docs:
            show_toast(self, "Veuillez sélectionner un document source à ajouter.", is_error=True)
            return

        if self.current_deck is None:
            show_toast(self, "Veuillez sélectionner un paquet cible.", is_error=True)
            return

        selected_engine = self.engine_combo.currentData()
        selected_pipeline = self.pipeline_combo.currentData()
        deck_name = getattr(self.current_deck, "name", "Général")
        model_name = getattr(self.current_model, "name", "Basique")
        pipe_name = getattr(selected_pipeline, "name", "Standard")

        added_count = 0
        for doc in checked_docs:
            persisted_chunks = self._resolve_batch_chunks(doc)
            selected_chunks: list[dict[str, Any]] = []

            scope_res = self._batch_scope_results.get(int(doc.id)) if getattr(doc, "id", None) else None
            if scope_res and scope_res.get("chunks"):
                selected_chunks = list(scope_res["chunks"])
            elif self._segment_inspector_doc and getattr(self._segment_inspector_doc, "id", None) == doc.id and hasattr(self, "segment_inspector"):
                active_segs = self.segment_inspector.get_active_segments()
                # Si l'utilisateur a des segments actifs qui ne sont pas le fallback 'Document Complet'
                if active_segs and any(s.get("title") != "Document Complet" for s in active_segs):
                    selected_chunks = active_segs
                elif persisted_chunks:
                    selected_chunks = persisted_chunks
            elif persisted_chunks:
                selected_chunks = persisted_chunks

            base_task_data: dict[str, Any] = {
                "doc": doc,
                "deck": self.current_deck,
                "deck_name": deck_name,
                "note_type": self.current_model,
                "model_name": model_name,
                "engine": selected_engine,
                "pipeline": selected_pipeline,
                "pipeline_name": pipe_name,
                "use_vision": self.cb_vision.isChecked(),
                "auto_val": self.cb_autoval.isChecked(),
                "temperature": self.slider_temp.value() / 10.0,
                "max_tokens": self.slider_tokens.value() * 1024,
                "status": "En attente",
                "progress_pct": 0,
                "cards_count": 0,
            }

            if selected_chunks and len(selected_chunks) > 0:
                for chunk_index, chunk in enumerate(selected_chunks):
                    chunk_content = str(chunk.get("content", "")).strip()
                    if not chunk_content:
                        continue
                    chunk_title = str(chunk.get("title") or chunk.get("heading_path") or f"Section {chunk_index + 1}")
                    chunk_task = {
                        **base_task_data,
                        "doc_title": f"{doc.title} — {chunk_title}",
                        "doc_content": chunk_content,
                        "source_chunks": [chunk],
                        "chunk_label": chunk_title,
                        "chunk_index": chunk_index,
                        "tokens_est": int(chunk.get("tokens") or len(chunk_content.split()) * 1.3),
                    }
                    self.queue_tasks_data.append(chunk_task)
                    added_count += 1
            else:
                doc_content = getattr(doc, "content", "") or ""
                words_count = len(doc_content.split())
                tokens_est = int(words_count * 1.3) if words_count > 0 else 25000
                self.queue_tasks_data.append(
                    {
                        **base_task_data,
                        "doc_title": doc.title,
                        "doc_content": doc_content,
                        "source_chunks": [],
                        "tokens_est": tokens_est,
                    }
                )
                added_count += 1

        self._update_queue_table()
        self._update_estimates_summary()
        show_toast(self, f"{added_count} tâche(s) ajoutée(s) à la Queue !")

    @staticmethod
    def _resolve_batch_chunks(doc: DocumentModel) -> list[dict[str, Any]]:
        """Retourne les chunks du périmètre documentaire dans un ordre stable."""
        excluded: set[str] = set()
        raw_excluded = getattr(doc, "excluded_headings", None)
        if raw_excluded:
            try:
                excluded = {str(value).strip().casefold() for value in json.loads(raw_excluded) if str(value).strip()}
            except (TypeError, ValueError, json.JSONDecodeError):
                logger.warning("Exclusions de titres invalides pour le document %s.", getattr(doc, "id", None))

        chunks: list[dict[str, Any]] = []
        persisted = list(DocumentChunkModel.select().where(DocumentChunkModel.document == doc).order_by(DocumentChunkModel.chunk_index.asc()))
        if persisted:
            raw_chunks = [
                {
                    "id": chunk.id,
                    "index": chunk.chunk_index,
                    "content": chunk.content,
                    "content_hash": chunk.content_hash,
                    "heading_path": chunk.heading_path,
                    "page_number": chunk.page_number,
                }
                for chunk in persisted
            ]
        else:
            raw_chunks = ChunkingService.extract_chunks(doc.content or "", file_type=doc.file_type or "md", strategy=ChunkingService.preferred_strategy(doc.file_type))

        start_page = getattr(doc, "start_page", None)
        end_page = getattr(doc, "end_page", None)
        for index, chunk in enumerate(raw_chunks):
            content = str(chunk.get("content", "")).strip()
            heading_path_raw = str(chunk.get("heading_path") or "").strip()
            # Nettoyage des balises HTML résiduelles (spans de page Marker, <b>…) pour
            # un affichage et une traçabilité lisibles, même sur une base non re-indexée.
            heading_path = ChunkingService._clean_heading_text(heading_path_raw)
            page_number = chunk.get("page_number")
            if not content:
                continue
            if page_number is not None and ((start_page is not None and page_number < start_page) or (end_page is not None and page_number > end_page)):
                continue
            heading_lower = heading_path.casefold()
            if excluded and any(item == heading_lower or item in heading_lower for item in excluded):
                continue
            chunks.append(
                {
                    **chunk,
                    "index": index,
                    "title": heading_path or f"Chunk {index + 1}",
                    "content": content,
                    "content_hash": chunk.get("content_hash") or ChunkingService.hash_content(content),
                    "tokens": int(chunk.get("tokens") or len(content.split()) * 1.3),
                }
            )
        return chunks

    def _update_queue_table(self) -> None:
        self.queue_table.blockSignals(True)
        self.cell_widgets_map.clear()
        self.status_badges_map.clear()
        self.cards_items_map.clear()

        if not self.queue_tasks_data:
            self.queue_table.setRowCount(0)
            self.queue_table.hide()
            self.queue_empty.show()
            self.queue_table.blockSignals(False)
            return

        self.queue_empty.hide()
        self.queue_table.show()
        self.queue_table.clearSpans()
        self.queue_table.setRowCount(len(self.queue_tasks_data))

        for i, task in enumerate(self.queue_tasks_data):
            doc: DocumentModel = task["doc"]
            status: str = task.get("status", "En attente")
            progress_pct: int = task.get("progress_pct", 0)
            cards_count: int = task.get("cards_count", 0)

            # Col 0: Checkbox
            cb_item = QTableWidgetItem()
            cb_item.setCheckState(Qt.CheckState.Checked)
            self.queue_table.setItem(i, 0, cb_item)

            # Col 1: Badge Statut
            badge_color = DesignTokens.COLOR_YELLOW
            if status == "Succès":
                badge_color = DesignTokens.COLOR_GREEN
            elif status == "En cours":
                badge_color = DesignTokens.COLOR_BLUE
            elif status == "Erreur":
                badge_color = DesignTokens.COLOR_RED
            elif status == "Annulé":
                badge_color = DesignTokens.TEXT_MUTED

            status_badge = Badge(status, variant="status")
            apply_pill_style(status_badge, badge_color)
            self.status_badges_map[i] = status_badge
            self.queue_table.setCellWidget(i, 1, status_badge)

            # Col 2: Document source
            chunk_label = task.get("chunk_label")
            source_label = f"{doc.title} › {chunk_label}" if chunk_label else doc.title
            doc_item = QTableWidgetItem(source_label)
            doc_item.setIcon(load_phosphor_icon("ph.file-text", color=DesignTokens.COLOR_BLUE))
            doc_item.setToolTip(f"ID: {doc.id} | Type: {doc.file_type or 'doc'} | Mots: {len((task.get('doc_content') or doc.content or '').split())}")
            self.queue_table.setItem(i, 2, doc_item)

            # Col 3: Paquet cible
            deck_item = QTableWidgetItem(task.get("deck_name", "Général"))
            self.queue_table.setItem(i, 3, deck_item)

            # Col 4: Modèle
            model_item = QTableWidgetItem(task.get("model_name", "Basique"))
            self.queue_table.setItem(i, 4, model_item)

            # Col 5: Pipeline
            pipe_item = QTableWidgetItem(task.get("pipeline_name", "Standard"))
            self.queue_table.setItem(i, 5, pipe_item)

            # Col 6: Progrès
            p_color = DesignTokens.ACCENT_PRIMARY
            p_text = "En attente..."
            if status == "Succès":
                p_color = DesignTokens.COLOR_GREEN
                p_text = "Terminé"
            elif status == "En cours":
                p_color = DesignTokens.COLOR_BLUE
                p_text = f"{progress_pct}%"
            elif status == "Erreur":
                p_color = DesignTokens.COLOR_RED
                p_text = "Erreur"
            elif status == "Annulé":
                p_color = DesignTokens.TEXT_MUTED
                p_text = "Annulé"

            prog_widget = ProgressTableCellWidget(progress_pct=progress_pct, status_text=p_text, color=p_color)
            self.cell_widgets_map[i] = prog_widget
            self.queue_table.setCellWidget(i, 6, prog_widget)

            # Col 7: Cartes
            cards_text = f"{cards_count} cartes" if cards_count > 0 else "-"
            cards_item = QTableWidgetItem(cards_text)
            cards_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.cards_items_map[i] = cards_item
            self.queue_table.setItem(i, 7, cards_item)

            # Col 8: Action Supprimer
            btn_del = IconButton("ph.x", tooltip="Retirer de la queue", size=18)
            btn_del.clicked.connect(lambda _, row_idx=i: self._remove_from_queue(row_idx))

            del_widget = QWidget()
            del_layout = QHBoxLayout(del_widget)
            del_layout.setContentsMargins(0, 0, 0, 0)
            del_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            del_layout.addWidget(btn_del)

            self.queue_table.setCellWidget(i, 8, del_widget)

        self.queue_table.blockSignals(False)

    def _remove_from_queue(self, row_idx: int) -> None:
        if 0 <= row_idx < len(self.queue_tasks_data):
            self.queue_tasks_data.pop(row_idx)
            self._update_queue_table()
            self._update_estimates_summary()

    @Slot()
    def _on_clear_queue(self) -> None:
        self.queue_tasks_data.clear()
        self._update_queue_table()
        self._update_estimates_summary()
        show_toast(self, "File d'attente vidée.")

    def _update_estimates_summary(self) -> None:
        total_tokens = sum(task.get("tokens_est", 25000) for task in self.queue_tasks_data)
        count = len(self.queue_tasks_data)

        self.card_status.val_lbl.setText("En attente" if count > 0 else "Prêt")
        self.card_cards.val_lbl.setText(f"{self._total_cards_accumulated} cartes")
        self.card_cost.val_lbl.setText(f"${(total_tokens / 1000000 * 0.15):.2f}")

    def _set_running_ui_state(self, is_running: bool) -> None:
        """Met à jour l'apparence du bouton de lancement et des métriques."""
        if is_running:
            self.btn_start_pipeline.setText("Arrêter le Batch")
            self.btn_start_pipeline.setIcon(load_on_accent_icon("ph.stop"))
            self.btn_start_pipeline.setStyleSheet(f"""
                QPushButton {{
                    background-color: {DesignTokens.COLOR_RED};
                    border: 1px solid {DesignTokens.COLOR_RED};
                    color: {DesignTokens.TEXT_ON_ACCENT};
                    font-weight: bold;
                    padding: 6px 18px;
                    border-radius: 6px;
                    font-size: 12px;
                }}
                QPushButton:hover {{
                    background-color: {DesignTokens.COLOR_RED_TEXT};
                }}
            """)
            self.card_status.val_lbl.setText("En cours")
            self.card_status.val_lbl.setStyleSheet(f"color: {DesignTokens.COLOR_BLUE}; font-size: 15px; font-weight: bold; border: none; font-family: '{DesignTokens.FONT_CODE}';")
        else:
            self.btn_start_pipeline.setText("Démarrer Pipeline")
            self.btn_start_pipeline.setIcon(load_on_accent_icon("ph.play"))
            self.btn_start_pipeline.setStyleSheet(f"""
                QPushButton {{
                    background-color: {DesignTokens.COLOR_GREEN};
                    border: 1px solid {DesignTokens.COLOR_GREEN};
                    color: {DesignTokens.TEXT_ON_ACCENT};
                    font-weight: bold;
                    padding: 6px 18px;
                    border-radius: 6px;
                    font-size: 12px;
                }}
                QPushButton:hover {{
                    background-color: #059669;
                    border-color: #34d399;
                }}
            """)

    @Slot()
    def _on_start_batch(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            self._on_stop_batch()
            return

        if not self.queue_tasks_data:
            show_toast(self, "La file d'attente est vide ! Ajoutez des tâches avant de lancer.", is_error=True)
            return

        tasks_payloads: list[BatchTaskPayload | BatchTaskSnapshot] = []

        for idx, task in enumerate(self.queue_tasks_data):
            task["status"] = "En attente"
            task["progress_pct"] = 0
            task["cards_count"] = 0

            doc: DocumentModel = task["doc"]
            deck = task.get("deck")
            if not deck:
                deck_name = task.get("deck_name", "Général")
                deck, _ = DeckModel.get_or_create(name=deck_name)

            selected_nt = task.get("note_type")
            if isinstance(selected_nt, NoteTypeModel):
                note_type = selected_nt
            else:
                note_type = NoteTypeModel.select().first() or NoteTypeModel.create(name="Basic", fields_schema='["Front", "Back"]', templates="[]", css_style="")

            selected_pipeline = task.get("pipeline")
            pipeline_id = selected_pipeline.id if selected_pipeline and hasattr(selected_pipeline, "id") else 1
            pipe_name = getattr(selected_pipeline, "name", "Standard")

            selected_engine = task.get("engine")
            llm_id = selected_engine.id if selected_engine and hasattr(selected_engine, "id") else 1
            eng_display = getattr(selected_engine, "display_name", getattr(selected_engine, "name", "LLM"))
            llm_config = {
                "display_name": eng_display,
                "model_id": getattr(selected_engine, "model_id", "default"),
                "context_limit": int(getattr(selected_engine, "context_limit", 128000) or 128000),
                "max_tokens": int(task.get("max_tokens") or getattr(selected_engine, "max_tokens", 16384) or 16384),
                "api_key": getattr(selected_engine, "api_key", ""),
                "provider": getattr(selected_engine, "provider", getattr(selected_engine, "provider_type", "openai")),
            }

            fields_schema = json.loads(note_type.fields_schema) if note_type.fields_schema else ["Front", "Back"]
            templates = json.loads(note_type.templates) if note_type.templates else []

            payload = BatchTaskPayload(
                task_index=idx,
                doc_id=doc.id,
                doc_title=str(task.get("doc_title") or doc.title),
                doc_content=str(task.get("doc_content") or getattr(doc, "content", "") or ""),
                deck_id=deck.id,
                deck_name=deck.name,
                model_id=note_type.id,
                model_name=note_type.name,
                note_type_fields=fields_schema,
                note_type_templates=templates,
                pipeline_id=pipeline_id,
                pipeline_name=pipe_name,
                llm_id=llm_id,
                llm_config=llm_config,
                chunk_strategy="auto",
                use_vision=bool(task.get("use_vision", False)),
                auto_validation=bool(task.get("auto_val", True)),
                temperature=float(task.get("temperature", 0.7)),
                max_tokens=int(task.get("max_tokens", 16384)),
                process_full_document=False,
                source_chunks=list(task.get("source_chunks", [])),
            )
            tasks_payloads.append(payload)

        self._update_queue_table()
        self.start_timestamp = time.time()
        self._total_cards_accumulated = 0

        self._set_running_ui_state(True)
        self._log_formatted_line("INFO", f"Initialisation du pipeline de traitement par lots ({len(tasks_payloads)} tâche(s))...")

        self.worker = BatchWorker(tasks=tasks_payloads)
        self.worker.task_started.connect(self._on_task_started)
        self.worker.task_progress.connect(self._on_task_progress)
        self.worker.task_completed.connect(self._on_task_completed)
        self.worker.task_failed.connect(self._on_task_failed)
        self.worker.log.connect(self._log_formatted_line)
        self.worker.batch_finished.connect(self._on_batch_finished)
        self.worker.cancelled.connect(self._on_batch_cancelled)

        self.worker.start()

    @Slot()
    def _on_stop_batch(self) -> None:
        if self.worker and self.worker.isRunning():
            self._log_formatted_line("WARN", "Arrêt demandé par l'utilisateur. En attente de terminaison...")
            self.worker.cancel()

    @Slot(int, str)
    def _on_task_started(self, task_idx: int, doc_title: str) -> None:
        if 0 <= task_idx < len(self.queue_tasks_data):
            self.queue_tasks_data[task_idx]["status"] = "En cours"
            if task_idx in self.status_badges_map:
                self.status_badges_map[task_idx].setText("En cours")
                apply_pill_style(self.status_badges_map[task_idx], DesignTokens.COLOR_BLUE)
            if task_idx in self.cell_widgets_map:
                self.cell_widgets_map[task_idx].update_progress(0, "Démarrage...", color=DesignTokens.COLOR_BLUE)

        total = len(self.queue_tasks_data)
        self.card_status.val_lbl.setText(f"En cours ({task_idx + 1}/{total})")

    @Slot(int, int, str)
    def _on_task_progress(self, task_idx: int, progress_pct: int, step_detail: str) -> None:
        if 0 <= task_idx < len(self.queue_tasks_data):
            self.queue_tasks_data[task_idx]["progress_pct"] = progress_pct
            if task_idx in self.cell_widgets_map:
                self.cell_widgets_map[task_idx].update_progress(progress_pct, step_detail, color=DesignTokens.COLOR_BLUE)

        if self.start_timestamp > 0:
            elapsed = int(time.time() - self.start_timestamp)
            mins = elapsed // 60
            secs = elapsed % 60
            self.card_time.val_lbl.setText(f"{mins:02d}:{secs:02d}")

    @Slot(int, list, int)
    def _on_task_completed(self, task_idx: int, prepared_notes: list[dict[str, Any]], cards_count: int) -> None:
        if 0 <= task_idx < len(self.queue_tasks_data):
            task = self.queue_tasks_data[task_idx]
            task["status"] = "Succès"
            task["progress_pct"] = 100
            task["cards_count"] = cards_count

            # Sauvegarde atomique en base
            deck_id = task["deck"].id if hasattr(task.get("deck"), "id") else 1
            model_id = task["note_type"].id if hasattr(task.get("note_type"), "id") else 1
            doc_id = task["doc"].id if hasattr(task.get("doc"), "id") else 0
            self._save_extracted_notes_to_db(prepared_notes, deck_id, model_id, doc_id)

            if task_idx in self.status_badges_map:
                self.status_badges_map[task_idx].setText("Succès")
                apply_pill_style(self.status_badges_map[task_idx], DesignTokens.COLOR_GREEN)

            if task_idx in self.cell_widgets_map:
                self.cell_widgets_map[task_idx].update_progress(100, "Terminé", color=DesignTokens.COLOR_GREEN)

            if task_idx in self.cards_items_map:
                self.cards_items_map[task_idx].setText(f"{cards_count} cartes")

            self._total_cards_accumulated += cards_count
            self.card_cards.val_lbl.setText(f"{self._total_cards_accumulated} cartes")

    @Slot(int, str)
    def _on_task_failed(self, task_idx: int, error_message: str) -> None:
        if 0 <= task_idx < len(self.queue_tasks_data):
            task = self.queue_tasks_data[task_idx]
            task["status"] = "Erreur"
            task["progress_pct"] = 100
            task["error_message"] = error_message

            if task_idx in self.status_badges_map:
                self.status_badges_map[task_idx].setText("Erreur")
                apply_pill_style(self.status_badges_map[task_idx], DesignTokens.COLOR_RED)

            if task_idx in self.cell_widgets_map:
                self.cell_widgets_map[task_idx].update_progress(100, "Échec", color=DesignTokens.COLOR_RED)

    def accept_batch_task(self, task_idx: int, accepted_cards: list[dict[str, Any]] | None = None) -> bool:
        """Persist the reviewed cards for one new scope-based queue row."""
        if not 0 <= task_idx < len(self.queue_tasks_data):
            return False
        task = self.queue_tasks_data[task_idx]
        pending = accepted_cards if accepted_cards is not None else list(task.get("pending_cards", []))
        original_count = len(task.get("pending_cards", []))
        if task.get("scope_snapshot") is None or not pending:
            return False
        fields = getattr(task.get("note_type"), "fields_schema", "[]") or "[]"
        try:
            expected_fields = json.loads(fields) if isinstance(fields, str) else fields
        except json.JSONDecodeError:
            expected_fields = ["Front", "Back"]
        if any(not all(str(card.get(field, "")).strip() for field in expected_fields) for card in pending):
            raise ValueError("Chaque carte acceptée doit contenir tous les champs requis.")
        self._save_extracted_notes_to_db(
            pending,
            task["deck"].id if hasattr(task.get("deck"), "id") else 1,
            task["note_type"].id if hasattr(task.get("note_type"), "id") else 1,
            task["doc"].id if hasattr(task.get("doc"), "id") else 0,
        )
        task["pending_cards"] = pending
        task["status"] = "Acceptée" if len(pending) == original_count else "Partielle"
        self._update_queue_table()
        return True

    def reject_batch_task(self, task_idx: int) -> bool:
        """Discard a pending scope result without writing it to the database."""
        if not 0 <= task_idx < len(self.queue_tasks_data):
            return False
        task = self.queue_tasks_data[task_idx]
        if task.get("scope_snapshot") is None:
            return False
        task["pending_cards"] = []
        task["status"] = "Rejetée"
        self._update_queue_table()
        return True

    def _save_extracted_notes_to_db(self, notes_data: list[dict[str, Any]], deck_id: int, model_id: int, doc_id: int = 0) -> None:
        try:
            deck = DeckModel.get_by_id(deck_id)
            note_type = NoteTypeModel.get_by_id(model_id)
            doc = DocumentModel.get_or_none(DocumentModel.id == doc_id) if doc_id else None
            templates = json.loads(note_type.templates) if note_type.templates else []
            is_cloze = any("{{cloze:" in t.get("qfmt", "") or "{{cloze:" in t.get("afmt", "") for t in templates)

            from ankiforge.services.audit.coverage_alignment_service import CoverageAlignmentService

            def _build_note_tags(raw: dict[str, Any]) -> list[str]:
                """Construit les tags de traçabilité fins pour une note de la file batch."""
                common_tags = ["AnkiForge_Batch"]
                if not doc:
                    return build_document_tags(extra_tags=common_tags)
                documentation_enabled = raw.get("_documentation_enabled", True)
                if not documentation_enabled:
                    return build_document_tags(doc_id=doc.id, doc_title=doc.title, extra_tags=common_tags)

                chunk_id = raw.get("_source_chunk_id")
                heading_path = raw.get("_source_heading_path")
                page_number = raw.get("_source_page_number")
                card_text = " ".join(str(v) for k, v in raw.items() if not str(k).startswith("_source_") and str(v).strip()).strip()
                resolved = CoverageAlignmentService.resolve_finest_chunk_for_card(
                    card_text=card_text,
                    doc_id=doc.id,
                    llm_section=str(heading_path) if heading_path else None,
                    source_chunk_id=int(chunk_id) if isinstance(chunk_id, int) else (int(chunk_id) if str(chunk_id).isdigit() else None),
                    page_number=int(page_number) if page_number is not None and str(page_number).isdigit() else None,
                )
                if resolved:
                    return build_document_tags(
                        doc_id=doc.id,
                        doc_title=doc.title,
                        page_number=resolved.page_number,
                        section_name=resolved.heading_path,
                        chunk_id=resolved.id,
                        extra_tags=common_tags,
                    )
                return build_document_tags(
                    doc_id=doc.id,
                    doc_title=doc.title,
                    page_number=int(page_number) if page_number is not None and str(page_number).isdigit() else None,
                    section_name=str(heading_path) if heading_path else None,
                    extra_tags=common_tags,
                )

            created_cards_count = 0
            with db.atomic():
                for raw_fields in notes_data:
                    tags_list = _build_note_tags(raw_fields)
                    cleaned_fields = {key: value for key, value in raw_fields.items() if not key.startswith("_source_")}
                    note = NoteModel.create(
                        guid=str(uuid.uuid4())[:10],
                        note_type=note_type,
                        tags=json.dumps(tags_list, ensure_ascii=False),
                        status="pending",
                    )
                    NoteVersionModel.create(
                        note=note,
                        version_number=1,
                        content=json.dumps(cleaned_fields, ensure_ascii=False),
                        source="ai_batch",
                        is_active=True,
                    )

                    if is_cloze:
                        max_cloze = get_max_cloze_index(cleaned_fields)
                        num_cards = max(1, max_cloze)
                        for i in range(num_cards):
                            CardModel.create(note=note, deck=deck, template_index=i)
                            created_cards_count += 1
                    else:
                        for idx, _ in enumerate(templates):
                            CardModel.create(note=note, deck=deck, template_index=idx)
                            created_cards_count += 1

            if created_cards_count and doc:
                try:
                    from ankiforge.services.audit.coverage_alignment_service import CoverageAlignmentService

                    CoverageAlignmentService.sync_coverage_from_tags(doc_id=doc.id)
                except Exception as err:
                    logger.debug("Synchronisation de la couverture ignorée : %s", err)

            self._log_formatted_line("SUCCESS", f"Enregistrement BDD : {len(notes_data)} note(s) ({created_cards_count} carte(s)) dans '{deck.name}'.")
        except Exception as e:
            logger.exception("Erreur lors de la sauvegarde batch : %s", e)
            self._log_formatted_line("ERROR", f"Échec sauvegarde BDD : {str(e)}")

    @Slot(int, int, int)
    def _on_batch_finished(self, success_count: int, error_count: int, total_cards: int) -> None:
        self._set_running_ui_state(False)
        self.card_status.val_lbl.setText("Terminé" if error_count == 0 else "Partiel")
        col = DesignTokens.COLOR_GREEN if error_count == 0 else DesignTokens.COLOR_YELLOW
        self.card_status.val_lbl.setStyleSheet(f"color: {col}; font-size: 15px; font-weight: bold; border: none; font-family: '{DesignTokens.FONT_CODE}';")

        if self.start_timestamp > 0:
            elapsed = int(time.time() - self.start_timestamp)
            mins = elapsed // 60
            secs = elapsed % 60
            self.card_time.val_lbl.setText(f"{mins:02d}:{secs:02d}")

        self._log_formatted_line("SUCCESS", f"Batch terminé : {success_count} job(s) réussi(s), {error_count} erreur(s) ({total_cards} cartes créées).")
        show_toast(self, f"Batch terminé : {success_count} réussis, {error_count} erreurs ({total_cards} cartes créées)")

    @Slot()
    def _on_batch_cancelled(self) -> None:
        self._set_running_ui_state(False)
        self.card_status.val_lbl.setText("Interrompu")
        self.card_status.val_lbl.setStyleSheet(f"color: {DesignTokens.COLOR_YELLOW}; font-size: 15px; font-weight: bold; border: none; font-family: '{DesignTokens.FONT_CODE}';")
        self._log_formatted_line("WARN", "Traitement par lots interrompu par l'utilisateur.")
        show_toast(self, "Batch interrompu par l'utilisateur.", is_error=False)

        self._update_queue_table()

    @Slot(str)
    def _on_batch_error(self, error_msg: str) -> None:
        self.card_status.val_lbl.setText("Erreur")
        self.card_status.val_lbl.setStyleSheet(f"color: {DesignTokens.COLOR_RED}; font-size: 16px; font-weight: bold; border: none; font-family: '{DesignTokens.FONT_CODE}';")
        self._log_formatted_line("ERROR", error_msg)
        log_and_notify_error(error_msg, context="Exécution du pipeline", parent=self, title="Erreur Pipeline")

    def refresh_theme(self, profile: Any) -> None:
        if hasattr(self, "card_status"):
            self.card_status.refresh_theme(profile)
        if hasattr(self, "card_time"):
            self.card_time.refresh_theme(profile)
        if hasattr(self, "card_cards"):
            self.card_cards.refresh_theme(profile)
        if hasattr(self, "card_cost"):
            self.card_cost.refresh_theme(profile)

        if hasattr(self, "lbl_src"):
            self.lbl_src.setStyleSheet(f"color: {profile.text_secondary}; font-size: 11px; font-weight: bold;")

        if hasattr(self, "btn_select_deck"):
            self.btn_select_deck.setIcon(load_phosphor_icon("ph.folder-open", color=profile.text_muted))
            self.btn_select_deck.setStyleSheet(
                f"text-align: left; padding: 6px 10px; border-radius: 4px; "
                f"border: 1px solid {profile.border_color}; background: {profile.bg_input}; "
                f"color: {profile.text_primary}; font-weight: normal;"
            )

        if hasattr(self, "btn_select_model"):
            self.btn_select_model.setIcon(load_phosphor_icon("ph.file-code", color=profile.text_muted))
            self.btn_select_model.setStyleSheet(
                f"text-align: left; padding: 6px 10px; border-radius: 4px; "
                f"border: 1px solid {profile.border_color}; background: {profile.bg_input}; "
                f"color: {profile.text_primary}; font-weight: normal;"
            )

        if hasattr(self, "cb_vision"):
            self.cb_vision.apply_theme_profile(profile)
        if hasattr(self, "cb_autoval"):
            self.cb_autoval.apply_theme_profile(profile)

        if hasattr(self, "adv_lbl"):
            self.adv_lbl.setStyleSheet(f"color: {profile.text_primary}; font-size: 12px; background: transparent;")
        if hasattr(self, "advanced_icon"):
            self.advanced_icon.setPixmap(load_phosphor_icon("ph.caret-right", color=profile.text_muted).pixmap(14, 14))

        if hasattr(self, "advanced_container"):
            self.advanced_container.setStyleSheet(f"""
                QFrame#batchAdvancedContainer {{
                    background: {profile.bg_input};
                    padding: 10px;
                    border-radius: {profile.radius_sm}px;
                    border: 1px solid {profile.border_color};
                }}
            """)

        if hasattr(self, "temp_lbl"):
            self.temp_lbl.setStyleSheet(f"color: {profile.text_secondary}; font-size: 11px;")
        if hasattr(self, "val_temp_lbl"):
            self.val_temp_lbl.setStyleSheet(f"color: {profile.text_primary}; font-family: '{profile.font_code}'; font-size: 11px;")
        if hasattr(self, "tokens_lbl"):
            self.tokens_lbl.setStyleSheet(f"color: {profile.text_secondary}; font-size: 11px;")
        if hasattr(self, "val_tokens_lbl"):
            self.val_tokens_lbl.setStyleSheet(f"color: {profile.text_primary}; font-family: '{profile.font_code}'; font-size: 11px;")

        if hasattr(self, "queue_table") and hasattr(self.queue_table, "refresh_theme"):
            self.queue_table.refresh_theme(profile)

        if hasattr(self, "console_output"):
            self.console_output.setStyleSheet(f"""
                QPlainTextEdit {{
                    background-color: {profile.bg_input};
                    color: {profile.color_green};
                    font-family: '{profile.font_code}';
                    font-size: 12px;
                    line-height: 1.6;
                    padding: 14px;
                    border: none;
                    selection-background-color: {profile.accent_primary};
                }}
            """)

        if hasattr(self, "btn_toggle_terminal") and hasattr(self.btn_toggle_terminal, "refresh_theme"):
            self.btn_toggle_terminal.refresh_theme(profile)

        for cell in self.cell_widgets_map.values():
            if hasattr(cell, "refresh_theme"):
                cell.refresh_theme(profile)

        from ankiforge.ui.components.panels import IdePanel

        for panel in self.findChildren(IdePanel):
            if hasattr(panel, "refresh_theme"):
                panel.refresh_theme(profile)


BatchTab = BatchView

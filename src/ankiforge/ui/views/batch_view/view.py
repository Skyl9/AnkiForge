from __future__ import annotations

import datetime
import json
import logging
import time
import uuid
from typing import Any

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
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
    DocumentModel,
    LLMConfigModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionModel,
    PipelineModel,
    db,
)
from ankiforge.services.workers.batch_worker import BatchTaskPayload, BatchWorker
from ankiforge.ui.components import (
    Badge,
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
from ankiforge.ui.dialogs.selection_dialog import SelectionDialog
from ankiforge.ui.theme import DesignTokens, apply_shadow
from ankiforge.ui.views.batch_view.constants import apply_pill_style
from ankiforge.ui.views.batch_view.widgets import (
    CicdMetricCard,
    ProgressTableCellWidget,
)
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.anki_renderer import get_max_cloze_index
from ankiforge.utils.icon_loader import load_phosphor_icon
from ankiforge.utils.logger import log_and_notify_error

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
        self.cell_widgets_map: dict[int, ProgressTableCellWidget] = {}
        self.start_timestamp = 0.0
        self.current_deck: DeckModel | None = None
        self.current_model: NoteTypeModel | None = None
        self.decks_cache: list[DeckModel] = []
        self.models_cache: list[NoteTypeModel] = []
        self._deck_modal: DeckSelectWindow | None = None

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

        self.card_status = CicdMetricCard("STATUT GLOBAL", "En attente", "ph.check-circle", color="#10b981")
        self.card_time = CicdMetricCard("TEMPS RESTANT", "--:--:--", "ph.timer", color="#3b82f6")
        self.card_cards = CicdMetricCard("CARTES GÉNÉRÉES", "0 / 0", "ph.cards", color="#6366f1")
        self.card_cost = CicdMetricCard("COÛT ESTIMÉ", "$0.00", "ph.coin", color="#eab308")

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
        build_main_layout.addWidget(scroll_area)

        # Section 1: Source
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
        src_ico.setPixmap(load_phosphor_icon("ph.file-text", color=DesignTokens.COLOR_BLUE).pixmap(14, 14))
        src_ico.setStyleSheet("border: none; background: transparent;")
        self.lbl_src = QLabel("SOURCE (FICHIERS/DOSSIERS)")
        self.lbl_src.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-weight: 700; font-size: 11px; letter-spacing: 0.5px; border: none; background: transparent;")
        src_top.addWidget(src_ico)
        src_top.addWidget(self.lbl_src)
        src_top.addStretch()
        src_layout.addLayout(src_top)

        self.doc_combo = StyledComboBox()
        self.doc_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.doc_combo.setMinimumContentsLength(8)
        self.doc_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        src_layout.addWidget(self.doc_combo)
        build_layout.addWidget(src_card)

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
        ai_layout.addWidget(self.pipeline_combo)

        self.btn_no_pipeline_help = SecondaryButton("Créer un Pipeline d'Agents")
        self.btn_no_pipeline_help.setIcon(load_phosphor_icon("ph.plus", color=DesignTokens.ACCENT_PRIMARY))
        self.btn_no_pipeline_help.setStyleSheet(f"color: {DesignTokens.ACCENT_PRIMARY}; border: 1px solid {DesignTokens.ACCENT_PRIMARY}; font-size: 11px;")
        self.btn_no_pipeline_help.hide()
        ai_layout.addWidget(self.btn_no_pipeline_help)

        opt_layout = QHBoxLayout()
        opt_layout.setContentsMargins(0, 4, 0, 0)
        opt_layout.setSpacing(6)

        self.cb_vision = OptionToggleRow("Vision (PDF)", icon_name="ph.eye", checked=True)
        self.cb_autoval = OptionToggleRow("Validation auto", icon_name="ph.shield-check", checked=True)

        opt_layout.addWidget(self.cb_vision, 1)
        opt_layout.addWidget(self.cb_autoval, 1)
        ai_layout.addLayout(opt_layout)

        build_layout.addWidget(ai_card)

        # Section 4: Paramètres Avancés
        self.btn_toggle_advanced = QPushButton()
        self.btn_toggle_advanced.setStyleSheet("background: transparent; border: none; text-align: left; padding: 4px 0;")
        self.btn_toggle_advanced.setCursor(Qt.CursorShape.PointingHandCursor)

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

        slider_style = f"""
            QSlider::groove:horizontal {{
                border-radius: 2px;
                height: 4px;
                margin: 0px;
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
            }}
            QSlider::sub-page:horizontal {{
                background-color: {DesignTokens.ACCENT_PRIMARY};
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background-color: #ffffff;
                border: 2px solid {DesignTokens.ACCENT_PRIMARY};
                height: 14px;
                width: 14px;
                margin: -5px 0;
                border-radius: 7px;
            }}
            QSlider::handle:horizontal:hover {{
                background-color: {DesignTokens.ACCENT_HOVER};
            }}
        """

        temp_layout = QVBoxLayout()
        temp_header = QHBoxLayout()
        self.temp_lbl = QLabel("Température")
        self.temp_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px; border: none; background: transparent;")
        self.val_temp_lbl = QLabel("0.7")
        self.val_temp_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-family: {DesignTokens.FONT_CODE}; font-size: 11px; border: none; background: transparent;")
        temp_header.addWidget(self.temp_lbl)
        temp_header.addStretch()
        temp_header.addWidget(self.val_temp_lbl)

        self.slider_temp = QSlider(Qt.Orientation.Horizontal)
        self.slider_temp.setMinimum(0)
        self.slider_temp.setMaximum(10)
        self.slider_temp.setValue(7)
        self.slider_temp.setStyleSheet(slider_style)
        self.slider_temp.valueChanged.connect(lambda v: self.val_temp_lbl.setText(f"{v / 10:.1f}"))

        temp_layout.addLayout(temp_header)
        temp_layout.addWidget(self.slider_temp)
        advanced_layout.addLayout(temp_layout)

        tokens_layout = QVBoxLayout()
        tokens_header = QHBoxLayout()
        self.tokens_lbl = QLabel("Max Tokens")
        self.tokens_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px; border: none; background: transparent;")
        self.val_tokens_lbl = QLabel("4096")
        self.val_tokens_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-family: {DesignTokens.FONT_CODE}; font-size: 11px; border: none; background: transparent;")
        tokens_header.addWidget(self.tokens_lbl)
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

        build_layout.addWidget(self.advanced_container)
        build_layout.addStretch()

        self.btn_add_to_queue = PrimaryButton("Ajouter à la Queue")
        self.btn_add_to_queue.setIcon(load_phosphor_icon("ph.plus", color="white"))
        apply_shadow(self.btn_add_to_queue, blur=20, offset_y=0, color="rgba(99, 102, 241, 0.75)")
        self.btn_add_to_queue.clicked.connect(self._on_add_to_queue_clicked)

        btn_container = QWidget()
        btn_layout = QVBoxLayout(btn_container)
        btn_layout.setContentsMargins(10, 8, 10, 10)
        btn_layout.addWidget(self.btn_add_to_queue)
        build_main_layout.addWidget(btn_container)

        self.build_panel.add_tab("Paramètres du Build", build_content, "ph.sliders-horizontal", closable=False)
        self.middle_splitter.addWidget(self.build_panel)

        # RIGHT PANEL
        self.queue_panel = IdePanel(detachable=True)

        self.btn_clear_table = IconButton("ph.trash", tooltip="Vider la file d'attente", size=22)
        self.btn_clear_table.clicked.connect(self._on_clear_queue)
        self.queue_panel.add_header_widget(self.btn_clear_table)

        self.btn_start_pipeline = PrimaryButton("Démarrer Pipeline")
        self.btn_start_pipeline.setIcon(load_phosphor_icon("ph.play", color="white"))
        self.btn_start_pipeline.setStyleSheet(f"""
            QPushButton {{
                background-color: {DesignTokens.COLOR_GREEN};
                border: 1px solid {DesignTokens.COLOR_GREEN};
                color: #ffffff;
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
        apply_shadow(self.btn_start_pipeline, blur=16, offset_y=0, color="rgba(16, 185, 129, 0.45)")
        self.btn_start_pipeline.clicked.connect(self._on_start_batch)
        self.queue_panel.add_header_widget(self.btn_start_pipeline)

        queue_content = QWidget()
        queue_layout = QVBoxLayout(queue_content)
        queue_layout.setContentsMargins(0, 0, 0, 0)
        queue_layout.setSpacing(0)

        self.queue_table = StyledTableWidget(["", "STATUT", "FICHIER / SOURCE", "PROGRÈS", "TOKENS EST.", "ACTIONS"])
        self.queue_table.setSelectionBehavior(StyledTableWidget.SelectionBehavior.SelectRows)
        self.queue_table.verticalHeader().setDefaultSectionSize(46)

        header = self.queue_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)

        self.queue_table.setColumnWidth(0, 36)
        self.queue_table.setColumnWidth(1, 110)
        self.queue_table.setColumnWidth(3, 160)
        self.queue_table.setColumnWidth(4, 100)
        self.queue_table.setColumnWidth(5, 70)

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

        self.queue_panel.add_tab("File d'attente détaillée", queue_content, "ph.list-dashes", closable=False)
        self.middle_splitter.addWidget(self.queue_panel)

        self.middle_splitter.setSizes([350, 750])
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

    def refresh_data(self) -> None:
        try:
            self.doc_combo.blockSignals(True)
            self.doc_combo.clear()
            docs = list(DocumentModel.select())
            if docs:
                for doc in docs:
                    self.doc_combo.addItem(f"📄 {doc.title}", userData=doc)
            else:
                self.doc_combo.addItem("Aucun document disponible")
            self.doc_combo.blockSignals(False)

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
            engines = list(LLMConfigModel.select())
            if not engines:
                LLMConfigModel.create(display_name="Claude 3.5 Sonnet", provider="anthropic", model_id="claude-3-5-sonnet-20240620", context_limit=200000)
                LLMConfigModel.create(display_name="GPT-4o", provider="openai", model_id="gpt-4o", context_limit=128000)
                engines = list(LLMConfigModel.select())
            if engines:
                for eg in engines:
                    display_name = getattr(eg, "display_name", getattr(eg, "name", str(eg)))
                    self.engine_combo.addItem(f"⚡ {display_name}", userData=eg)
                self.btn_no_engine_help.hide()
            else:
                self.btn_no_engine_help.show()
            self.engine_combo.blockSignals(False)

            self.pipeline_combo.blockSignals(True)
            self.pipeline_combo.clear()
            pipelines = list(PipelineModel.select())
            if not pipelines:
                PipelineModel.create(name="Excellence (Standard)", description="Archiviste + Linter")
                pipelines = list(PipelineModel.select())
            if pipelines:
                for pipe in pipelines:
                    self.pipeline_combo.addItem(f"🔀 {pipe.name}", userData=pipe)
                self.btn_no_pipeline_help.hide()
            else:
                self.btn_no_pipeline_help.show()
            self.pipeline_combo.blockSignals(False)

        except Exception as e:
            logger.warning("Erreur refresh_data batch_view: %s", e)

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

        level_color = "#3b82f6"
        if level == "WARN":
            level_color = "#eab308"
        elif level == "SUCCESS":
            level_color = "#10b981"
        elif level == "ERROR":
            level_color = "#ef4444"

        formatted_html = f"<span style='color: {DesignTokens.TEXT_MUTED}'>[{now_str}]</span> <span style='color: {level_color}; font-weight: bold;'>{level}</span> {msg}"
        self.console_output.appendHtml(formatted_html)

    @Slot()
    def _on_clear_terminal_clicked(self) -> None:
        self.console_output.clear()
        self._log_formatted_line("INFO", "Terminal logs cleared.")

    @Slot()
    def _on_browse_local_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(self, "Sélectionner un document source", "", "Documents (*.pdf *.txt *.md *.docx);;Tous (*)")
        if file_path:
            import os

            title = os.path.basename(file_path)
            doc, _ = DocumentModel.get_or_create(title=title, defaults={"file_path": file_path, "content": f"Contenu du fichier {title}"})
            self.refresh_data()
            show_toast(self, f"Document '{title}' chargé !")

    @Slot()
    def _on_add_to_queue_clicked(self) -> None:
        doc: DocumentModel | None = self.doc_combo.currentData()
        if not doc or not isinstance(doc, DocumentModel):
            show_toast(self, "Veuillez sélectionner un document source valide.", is_error=True)
            return

        if self.current_deck is None:
            show_toast(self, "Veuillez sélectionner un paquet cible.", is_error=True)
            return

        selected_engine = self.engine_combo.currentData()
        selected_pipeline = self.pipeline_combo.currentData()

        doc_content = getattr(doc, "content", "") or ""
        words_count = len(doc_content.split())
        tokens_est = int(words_count * 1.3) if words_count > 0 else 25000

        task_data = {
            "doc": doc,
            "deck_name": getattr(self.current_deck, "name", "Général"),
            "note_type": self.current_model,
            "engine": selected_engine,
            "pipeline": selected_pipeline,
            "use_vision": self.cb_vision.isChecked(),
            "auto_val": self.cb_autoval.isChecked(),
            "temperature": self.slider_temp.value() / 10.0,
            "max_tokens": self.slider_tokens.value() * 256,
            "status": "En attente",
            "tokens_est": tokens_est,
            "progress_pct": 0,
        }

        self.queue_tasks_data.append(task_data)
        self._update_queue_table()
        self._update_estimates_summary()
        show_toast(self, f"Tâche '{doc.title}' ajoutée à la Queue !")

    def _update_queue_table(self) -> None:
        self.queue_table.blockSignals(True)
        self.cell_widgets_map.clear()

        if not self.queue_tasks_data:
            self.queue_table.setRowCount(1)
            empty_item = QTableWidgetItem("La file d'attente est vide. Sélectionnez des documents à gauche pour commencer.")
            empty_item.setFlags(Qt.ItemFlag.NoItemFlags)
            empty_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.queue_table.setItem(0, 0, empty_item)
            self.queue_table.setSpan(0, 0, 1, 6)
            self.queue_table.blockSignals(False)
            return

        self.queue_table.clearSpans()
        self.queue_table.setRowCount(len(self.queue_tasks_data))

        for i, task in enumerate(self.queue_tasks_data):
            doc: DocumentModel = task["doc"]
            status: str = task.get("status", "En attente")
            tokens_est: int = task.get("tokens_est", 25000)
            progress_pct: int = task.get("progress_pct", 0)

            cb_item = QTableWidgetItem()
            cb_item.setCheckState(Qt.CheckState.Checked)
            self.queue_table.setItem(i, 0, cb_item)

            if status == "Succès":
                badge_color = DesignTokens.COLOR_GREEN
            elif status == "En cours":
                badge_color = DesignTokens.COLOR_BLUE
            elif status == "Erreur":
                badge_color = DesignTokens.COLOR_RED
            else:
                badge_color = DesignTokens.COLOR_YELLOW

            status_badge = Badge(status, variant="status")
            apply_pill_style(status_badge, badge_color)
            self.queue_table.setCellWidget(i, 1, status_badge)

            doc_item = QTableWidgetItem(f"📄 {doc.title}")
            self.queue_table.setItem(i, 2, doc_item)

            if status == "Succès":
                p_color = DesignTokens.COLOR_GREEN
                p_text = "Terminé"
            elif status == "En cours":
                p_color = DesignTokens.COLOR_BLUE
                p_text = "En cours..."
            elif status == "Erreur":
                p_color = DesignTokens.COLOR_RED
                p_text = "Erreur"
            else:
                p_color = DesignTokens.ACCENT_PRIMARY
                p_text = "En attente..."

            prog_widget = ProgressTableCellWidget(progress_pct=progress_pct, status_text=p_text, color=p_color)
            self.cell_widgets_map[i] = prog_widget
            self.queue_table.setCellWidget(i, 3, prog_widget)

            tokens_item = QTableWidgetItem(f"~ {tokens_est:,}")
            tokens_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.queue_table.setItem(i, 4, tokens_item)

            btn_del = IconButton("ph.x", tooltip="Retirer de la queue", size=18)
            btn_del.clicked.connect(lambda _, row_idx=i: self._remove_from_queue(row_idx))

            del_widget = QWidget()
            del_layout = QHBoxLayout(del_widget)
            del_layout.setContentsMargins(0, 0, 0, 0)
            del_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            del_layout.addWidget(btn_del)

            self.queue_table.setCellWidget(i, 5, del_widget)

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
        self.card_cards.val_lbl.setText(f"0 / {count}")
        self.card_cost.val_lbl.setText(f"${(total_tokens / 1000000 * 0.15):.2f}")

    @Slot()
    def _on_start_batch(self) -> None:
        if not self.queue_tasks_data:
            show_toast(self, "La file d'attente est vide ! Ajoutez des tâches avant de lancer.", is_error=True)
            return

        tasks_payloads: list[BatchTaskPayload] = []

        for task in self.queue_tasks_data:
            task["status"] = "En cours"
            doc: DocumentModel = task["doc"]
            deck_name: str = task["deck_name"]

            deck, _ = DeckModel.get_or_create(name=deck_name)

            selected_nt = task["note_type"]
            note_type = selected_nt if isinstance(selected_nt, NoteTypeModel) else NoteTypeModel.select().first()
            if not note_type:
                note_type = NoteTypeModel.create(name="Basic", fields_schema='["Front", "Back"]', templates="[]", css_style="")

            selected_pipeline = task["pipeline"]
            pipeline_id = selected_pipeline.id if selected_pipeline and hasattr(selected_pipeline, "id") else 1

            pipeline_steps = [
                {
                    "name": "BatchGenerator",
                    "system_prompt": 'Génère des cartes Anki sous forme de tableau JSON [{"front": "...", "back": "..."}].',
                    "output_format": "json",
                }
            ]

            selected_engine = task["engine"]
            llm_id = selected_engine.id if selected_engine and hasattr(selected_engine, "id") else 1
            eng_display = getattr(selected_engine, "display_name", getattr(selected_engine, "name", "LLM"))
            llm_config = {
                "display_name": eng_display,
                "model_id": getattr(selected_engine, "model_id", "default"),
                "context_limit": 128000,
                "api_key": getattr(selected_engine, "api_key", ""),
                "provider": getattr(selected_engine, "provider_type", "openai"),
            }

            fields_schema = json.loads(note_type.fields_schema) if note_type.fields_schema else ["Front", "Back"]
            templates = json.loads(note_type.templates) if note_type.templates else []

            payload = BatchTaskPayload(
                doc_id=doc.id,
                doc_title=doc.title,
                doc_content=getattr(doc, "content", ""),
                deck_id=deck.id,
                model_id=note_type.id,
                note_type_fields=fields_schema,
                note_type_templates=templates,
                pipeline_id=pipeline_id,
                pipeline_steps=pipeline_steps,
                llm_id=llm_id,
                llm_config=llm_config,
                chunk_strategy="Sémantique (Titres)",
                use_vision=task["use_vision"],
            )
            tasks_payloads.append(payload)

        self._update_queue_table()
        self.start_timestamp = time.time()

        self.card_status.val_lbl.setText("En cours")
        self.card_status.val_lbl.setStyleSheet(f"color: {DesignTokens.COLOR_BLUE}; font-size: 16px; font-weight: bold; border: none; font-family: '{DesignTokens.FONT_CODE}';")

        self._log_formatted_line("INFO", f"Starting build job for {len(tasks_payloads)} documents in queue...")

        ai_provider = None
        if self.ai_manager and hasattr(self.ai_manager, "get_active_provider"):
            try:
                ai_provider = self.ai_manager.get_active_provider()
            except Exception:
                pass  # nosec B110

        self.worker = BatchWorker(ai_provider=ai_provider, tasks=tasks_payloads)
        self.worker.batch_data_ready.connect(self._save_extracted_notes_to_db)
        self.worker.progress_val.connect(self._on_worker_progress_pct)
        self.worker.progress_text.connect(lambda txt: self._log_formatted_line("INFO", txt))
        self.worker.log.connect(lambda msg: self._log_formatted_line("INFO", msg))
        self.worker.finished.connect(self._on_batch_finished)
        self.worker.error.connect(self._on_batch_error)

        self.worker.start()

    @Slot(int)
    def _on_worker_progress_pct(self, val: int) -> None:
        if self.start_timestamp > 0:
            elapsed = int(time.time() - self.start_timestamp)
            mins = elapsed // 60
            secs = elapsed % 60
            self.card_time.val_lbl.setText(f"{mins:02d}:{secs:02d}")

        if 0 in self.cell_widgets_map:
            self.cell_widgets_map[0].update_progress(val, f"Génération IA ({val}%)...", color="#3b82f6")

    @Slot(list, int, int)
    def _save_extracted_notes_to_db(self, notes_data: list[dict[str, Any]], deck_id: int, model_id: int) -> None:
        try:
            deck = DeckModel.get_by_id(deck_id)
            note_type = NoteTypeModel.get_by_id(model_id)
            templates = json.loads(note_type.templates) if note_type.templates else []
            is_cloze = any("{{cloze:" in t.get("qfmt", "") or "{{cloze:" in t.get("afmt", "") for t in templates)

            new_count = 0
            with db.atomic():
                for cleaned_fields in notes_data:
                    note = NoteModel.create(
                        guid=str(uuid.uuid4())[:10],
                        note_type=note_type,
                        tags=json.dumps(["AnkiForge_Batch"], ensure_ascii=False),
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
                            new_count += 1
                    else:
                        for idx, _ in enumerate(templates):
                            CardModel.create(note=note, deck=deck, template_index=idx)
                            new_count += 1

            self.card_cards.val_lbl.setText(f"{new_count} / {len(self.queue_tasks_data)}")
            self._log_formatted_line("SUCCESS", f"Chunk validated by Linter Agent: {new_count} cards saved to deck '{deck.name}'")
        except Exception as e:
            logger.exception("Erreur lors de la sauvegarde batch : %s", e)
            self._log_formatted_line("ERROR", f"Save failed: {str(e)}")

    @Slot(int, int)
    def _on_batch_finished(self, success_count: int, error_count: int) -> None:
        self.card_status.val_lbl.setText("Terminé")
        self.card_status.val_lbl.setStyleSheet(f"color: {DesignTokens.COLOR_GREEN}; font-size: 16px; font-weight: bold; border: none; font-family: '{DesignTokens.FONT_CODE}';")
        self._log_formatted_line("SUCCESS", f"Pipeline finished cleanly. {success_count} jobs succeeded, {error_count} errors.")
        show_toast(self, f"Pipeline terminé : {success_count} jobs réussis !")

        for task in self.queue_tasks_data:
            task["status"] = "Terminé"
            task["progress_pct"] = 100

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
            self.cb_vision.setStyleSheet(f"""
                QWidget#optionToggleRow {{
                    background-color: {profile.bg_panel};
                    border: 1px solid {profile.border_color};
                    border-radius: 6px;
                }}
                QWidget#optionToggleRow:hover {{
                    border-color: {profile.accent_primary};
                }}
            """)
        if hasattr(self, "cb_autoval"):
            self.cb_autoval.setStyleSheet(f"""
                QWidget#optionToggleRow {{
                    background-color: {profile.bg_panel};
                    border: 1px solid {profile.border_color};
                    border-radius: 6px;
                }}
                QWidget#optionToggleRow:hover {{
                    border-color: {profile.accent_primary};
                }}
            """)

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

        slider_style = f"""
            QSlider {{
                min-height: 24px;
            }}
            QSlider::groove:horizontal {{
                border-radius: 2px;
                height: 4px;
                margin: 0px;
                background-color: {profile.bg_hover};
            }}
            QSlider::sub-page:horizontal {{
                background-color: {profile.accent_primary};
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background-color: {profile.accent_primary};
                border: none;
                height: 12px;
                width: 12px;
                margin: -4px 0;
                border-radius: 6px;
            }}
            QSlider::handle:horizontal:hover {{
                background-color: {profile.accent_hover};
            }}
        """
        if hasattr(self, "slider_temp"):
            self.slider_temp.setStyleSheet(slider_style)
        if hasattr(self, "slider_tokens"):
            self.slider_tokens.setStyleSheet(slider_style)

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

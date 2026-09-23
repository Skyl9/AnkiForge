from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSplitter,
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
from ankiforge.repositories.deck_repository import DeckRepository
from ankiforge.services.batch.models import (
    BatchGenerationConfig,
    BatchScopeSnapshot,
    BatchSourceBlock,
    BatchTaskSnapshot,
    BatchTaskStatus,
)
from ankiforge.services.batch.slicing_service import SliceUnit
from ankiforge.services.parsing.chunking_service import ChunkingService
from ankiforge.services.settings_service import SettingsService
from ankiforge.services.workers.batch_worker import BatchTaskPayload, BatchWorker
from ankiforge.ui.components import (
    IconButton,
    IdePanel,
    OptionToggleRow,
    PrimaryButton,
    SecondaryButton,
    StyledComboBox,
)
from ankiforge.ui.components.deck_select_window import DeckSelectWindow
from ankiforge.ui.dialogs.selection_dialog import SelectionDialog
from ankiforge.ui.theme import DesignTokens, apply_shadow
from ankiforge.ui.views.batch_view.dialogs import BatchSliceComposerDialog
from ankiforge.ui.views.batch_view.widgets import (
    BatchActivityLog,
    BatchMetricsBar,
    BatchQueueTable,
    BatchStagingPanel,
)
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
        self._total_cards_accumulated = 0
        self.start_timestamp = 0.0
        self._run_clock_timer: QTimer | None = None
        self.current_deck: DeckModel | None = None
        self.current_model: NoteTypeModel | None = None
        self.decks_cache: list[DeckModel] = []
        self.models_cache: list[NoteTypeModel] = []
        self._deck_modal: DeckSelectWindow | None = None
        self._last_composer_doc: DocumentModel | None = None  # doc réutilisé à la prochaine ouverture du composer
        # Staging panel: notes brutes par clé de rangée (reçues via task_completed / task_review_ready)
        self._prepared_notes_by_uid: dict[str, list[dict[str, Any]]] = {}
        self._logs_tab_idx: int = -1
        self._review_tab_idx: int = -1

        self._setup_ui()
        self._connect_signals()
        self.refresh_data()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # TOP ROW: Metrics Cards (barre KPI encapsulée dans BatchMetricsBar)
        self.metrics_bar = BatchMetricsBar(self)
        # Alias rétrocompatibles utilisés par BatchView et les tests
        self.card_status = self.metrics_bar.card_status
        self.card_time = self.metrics_bar.card_time
        self.card_cards = self.metrics_bar.card_cards
        self.card_cost = self.metrics_bar.card_cost
        main_layout.addWidget(self.metrics_bar)

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

        # Section 1: Composer le lot (fusion document + parties + modes d'insertion)
        compose_card = QFrame()
        compose_card.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)
        compose_layout = QVBoxLayout(compose_card)
        compose_layout.setContentsMargins(8, 8, 8, 8)
        compose_layout.setSpacing(6)

        compose_top = QHBoxLayout()
        compose_top.setContentsMargins(0, 0, 0, 0)
        compose_top.setSpacing(6)
        compose_ico = QLabel()
        compose_ico.setPixmap(load_phosphor_icon("ph.scissors", color=DesignTokens.COLOR_BLUE).pixmap(14, 14))
        compose_ico.setStyleSheet("border: none; background: transparent;")
        self.lbl_compose = QLabel("COMPOSER LE LOT")
        self.lbl_compose.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-weight: 700; font-size: 11px; letter-spacing: 0.5px; border: none; background: transparent;")
        compose_top.addWidget(compose_ico)
        compose_top.addWidget(self.lbl_compose)
        compose_top.addStretch()
        compose_layout.addLayout(compose_top)

        self.btn_compose_batch = PrimaryButton("Composer le lot…", tooltip="Choisir le document, son mode de découpage (direct / auto), puis ses parties")
        self.btn_compose_batch.setIcon(load_on_accent_icon("ph.plus"))
        apply_shadow(self.btn_compose_batch, blur=10, offset_y=2, color=DesignTokens.ACCENT_GLOW)
        self.btn_compose_batch.clicked.connect(self._on_open_batch_composer)
        compose_layout.addWidget(self.btn_compose_batch)

        compose_hint = QLabel("Flux unique : ouvrir le document → choisir le mode de découpage (Direct ou Auto) → sélectionner les parties → Ajouter à la Queue.")
        compose_hint.setWordWrap(True)
        compose_hint.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; border: none; background: transparent;")
        compose_layout.addWidget(compose_hint)

        build_layout.addWidget(compose_card)

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

        saved_autoval = SettingsService.get("batch/auto_validation", False)
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

        self.btn_resume_batch = SecondaryButton("Reprendre le Lot", tooltip="Relancer uniquement les documents non terminés ou en échec")
        self.btn_resume_batch.setIcon(load_phosphor_icon("ph.arrow-counter-clockwise", color=DesignTokens.COLOR_YELLOW))
        self.btn_resume_batch.setVisible(False)
        self.btn_resume_batch.clicked.connect(self._on_resume_batch)
        self.queue_panel.add_header_widget(self.btn_resume_batch)

        queue_content = QWidget()
        queue_layout = QVBoxLayout(queue_content)
        queue_layout.setContentsMargins(0, 0, 0, 0)
        queue_layout.setSpacing(0)

        # Tableau de bord de la file (table, filtres et rendu encapsulés dans BatchQueueTable)
        self.queue_widget = BatchQueueTable(queue_content)
        self.queue_table = self.queue_widget.table
        self.queue_empty = self.queue_widget.queue_empty
        self.queue_widget.review_requested.connect(self._on_open_staging_for_task)
        self.queue_widget.remove_requested.connect(self._remove_from_queue)
        self.queue_widget.retry_requested.connect(self._on_retry_task)
        queue_layout.addWidget(self.queue_widget, 1)

        self.queue_panel.add_tab("File d'attente détaillée", queue_content, "ph.list-dashes", closable=False)
        self.middle_splitter.addWidget(self.queue_panel)

        self.middle_splitter.setSizes([400, 700])
        self.main_splitter.addWidget(self.middle_splitter)

        # BOTTOM ROW
        self.terminal_panel = IdePanel(detachable=True)
        self._terminal_expanded = True
        self._terminal_last_height: int = 240
        self._terminal_min_height: int = self.terminal_panel.minimumHeight()

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

        # Journal d'activité moderne (remplace la QPlainTextEdit verte)
        self.activity_log = BatchActivityLog(self.terminal_content)
        # Alias rétrocompatible utilisé dans _log_formatted_line et les tests
        self.console_output: BatchActivityLog = self.activity_log
        terminal_layout.addWidget(self.activity_log, 1)

        self._logs_tab_idx = self.terminal_panel.add_tab("root@ankiforge:~/pipeline_logs", self.terminal_content, "ph.terminal-window", closable=False)
        self.main_splitter.addWidget(self.terminal_panel)

        # STAGING PANEL (Revue & Staging) : onglet permanent non fermable du terminal,
        # accolé aux logs. L'utilisateur ne "perd" plus la revue au gré des phases du batch.
        self.staging_panel = BatchStagingPanel(parent=self.terminal_panel)
        self.staging_panel.set_save_callback(self._save_extracted_notes_to_db)
        self.staging_panel.cards_accepted.connect(self._on_staging_accepted)
        self.staging_panel.task_rejected.connect(self._on_staging_rejected)
        self._review_tab_idx = self.terminal_panel.add_tab("Revue", self.staging_panel, "ph.magnifying-glass", closable=False)
        self.terminal_panel.set_active_tab(self._logs_tab_idx)
        self.staging_panel.set_review_tasks_provider(self._staging_task_list)
        if hasattr(self.metrics_bar, "staging_review_requested"):
            self.metrics_bar.staging_review_requested.connect(self._on_open_staging_badge)

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

    def _terminal_splitter_index(self) -> int:
        """Index du panneau terminal dans main_splitter (robuste quel que soit le nombre d'enfants)."""
        for i in range(self.main_splitter.count()):
            if self.main_splitter.widget(i) is self.terminal_panel:
                return i
        return -1

    def _apply_terminal_space(self, height: int) -> None:
        """Alloue une hauteur au seul panneau terminal (D6 : ne pas réécrire les autres enfants)."""
        idx = self._terminal_splitter_index()
        if idx < 0:
            return
        sizes = list(self.main_splitter.sizes())
        if len(sizes) <= idx:
            return
        sizes[idx] = height
        self.main_splitter.setSizes(sizes)

    def _toggle_terminal(self) -> None:
        self._terminal_expanded = not self._terminal_expanded
        if self._terminal_expanded:
            self.terminal_panel.setMinimumHeight(self._terminal_min_height)
            self.terminal_content.setVisible(True)
            self.btn_toggle_terminal.setIcon(load_phosphor_icon("ph.caret-down", color=DesignTokens.TEXT_SECONDARY))
            self._apply_terminal_space(max(self._terminal_last_height, 60))
        else:
            idx = self._terminal_splitter_index()
            sizes = self.main_splitter.sizes()
            if 0 <= idx < len(sizes) and sizes[idx] > 50:
                self._terminal_last_height = sizes[idx]
            self.terminal_panel.setMinimumHeight(36)
            self.terminal_content.setVisible(False)
            self.btn_toggle_terminal.setIcon(load_phosphor_icon("ph.caret-up", color=DesignTokens.TEXT_SECONDARY))
            self._apply_terminal_space(36)

    def _connect_signals(self) -> None:
        self.btn_select_deck.clicked.connect(self._on_click_select_deck)
        self.btn_select_model.clicked.connect(self._on_click_select_model)
        self.btn_toggle_advanced.clicked.connect(self._toggle_advanced_settings)
        self.btn_no_engine_help.clicked.connect(self._open_settings_modal)
        self.btn_no_pipeline_help.clicked.connect(lambda: show_toast(self, "Créez un pipeline dans l'onglet Pipelines."))

    def refresh_data(self) -> None:
        try:
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
        if hasattr(self, "activity_log"):
            self.activity_log.append_log(level, msg)

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

    def _ensure_queue_uids(self) -> None:
        """Garantit une clé de rangée `_queue_uid` stable à chaque rangée (résilience legacy/tests)."""
        for task in self.queue_tasks_data:
            task.setdefault("_queue_uid", str(uuid.uuid4()))

    @staticmethod
    def _task_uid(task: dict[str, Any]) -> str:
        """Clé de rangée « _queue_uid » d'une tâche (chaîne vide si absente)."""
        return str(task.get("_queue_uid") or "")

    def _update_queue_table(self) -> None:
        """Délègue le rendu complet de la file d'attente au widget BatchQueueTable."""
        self._ensure_queue_uids()
        self.queue_widget.set_tasks(self.queue_tasks_data)
        self._refresh_review_badge()

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

    def _start_run_clock(self) -> None:
        """Horloge temps écoulé du run, battante même sans événements de progression.

        Régression : le chrono « Temps » ne bougeait que sur les signaux de progression ;
        un appel LLM unique sans sous-étapes (ex. Gemini afflué) gelait l'affichage → impression
        d'UI bloquée. Un ticker 500 ms maintient l'horloge visible et prouve que la génération tourne.
        """
        if self._run_clock_timer is not None:
            self._run_clock_timer.stop()
        self._run_clock_timer = QTimer(self)
        self._run_clock_timer.setInterval(500)
        self._run_clock_timer.timeout.connect(self._tick_run_clock)
        self._run_clock_timer.start()
        self._tick_run_clock()

    def _tick_run_clock(self) -> None:
        if self.start_timestamp <= 0:
            return
        elapsed = int(time.time() - self.start_timestamp)
        mins, secs = divmod(elapsed, 60)
        self.card_time.val_lbl.setText(f"{mins:02d}:{secs:02d}")

    def _stop_run_clock(self) -> None:
        if self._run_clock_timer is not None:
            self._run_clock_timer.stop()

    @Slot()
    def _on_start_batch(self, resume_incomplete: bool = False) -> None:
        if self.worker is not None and self.worker.isRunning():
            self._on_stop_batch()
            return

        if not self.queue_tasks_data:
            show_toast(self, "La file d'attente est vide ! Ajoutez des tâches avant de lancer.", is_error=True)
            return

        tasks_payloads: list[BatchTaskPayload | BatchTaskSnapshot] = []

        skipped_successful_count = 0
        for idx, task in enumerate(self.queue_tasks_data):
            prev_status = str(task.get("status", "En attente"))
            if prev_status in ("Succès", "Acceptée"):
                skipped_successful_count += 1
                continue

            task["status"] = "En attente"
            task["progress_pct"] = 0
            task["cards_count"] = 0

            doc: DocumentModel = task["doc"]
            deck = task.get("deck")
            if not deck:
                deck_name = task.get("deck_name", "Général")
                deck = DeckRepository().get_or_create_deck_hierarchical(deck_name)

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
            raw_llm_config: dict[str, Any] = task.get("llm_config") or {}
            llm_config = {
                "display_name": str(raw_llm_config.get("display_name") or eng_display),
                "model_id": str(raw_llm_config.get("model_id") or getattr(selected_engine, "model_id", "default")),
                "context_limit": int(raw_llm_config.get("context_limit") or getattr(selected_engine, "context_limit", 128000) or 128000),
                "max_tokens": int(task.get("max_tokens") or raw_llm_config.get("max_tokens") or getattr(selected_engine, "max_tokens", 16384) or 16384),
                "api_key": str(raw_llm_config.get("api_key") or getattr(selected_engine, "api_key", "")),
                "provider": str(raw_llm_config.get("provider") or getattr(selected_engine, "provider", getattr(selected_engine, "provider_type", "openai"))),
            }

            fields_schema = json.loads(note_type.fields_schema) if note_type.fields_schema else ["Front", "Back"]
            templates = json.loads(note_type.templates) if note_type.templates else []

            scope = self._snapshot_scope_for_task(task)
            if scope is not None:
                # Protocole scopes : portée figée + config → BatchTaskSnapshot exécuté par le worker.
                task["_is_snapshot_task"] = True
                snapshot = BatchTaskSnapshot.create(
                    scope=scope,
                    config=BatchGenerationConfig(
                        pipeline_id=pipeline_id,
                        pipeline_name=pipe_name,
                        llm_id=llm_id,
                        llm_config=llm_config,
                        deck_id=deck.id,
                        deck_name=deck.name,
                        model_id=note_type.id,
                        model_name=note_type.name,
                        note_type_fields=tuple(fields_schema),
                        note_type_templates=tuple(templates),
                        auto_validation=bool(task.get("auto_val", True)),
                        use_vision=bool(task.get("use_vision", False)),
                        temperature=float(task.get("temperature", 0.7)),
                        max_tokens=int(task.get("max_tokens", 16384)),
                        strict_source_grounding=bool(task.get("strict_source_grounding", True)),
                    ),
                    task_index=idx,
                )
                task["_batch_task_id"] = snapshot.task_id
                tasks_payloads.append(snapshot)
            else:
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
                    extra_metadata={"status": prev_status, "cards_count": task.get("cards_count", 0)},
                )
                tasks_payloads.append(payload)

        if not tasks_payloads:
            show_toast(self, "Toutes les tâches de la file sont déjà terminées avec succès.", is_error=False)
            return

        self._update_queue_table()
        self.start_timestamp = time.time()
        self._total_cards_accumulated = sum(int(t.get("cards_count", 0)) for t in self.queue_tasks_data if t.get("status") in ("Succès", "Acceptée"))
        self.card_cards.val_lbl.setText(f"{self._total_cards_accumulated} cartes")

        self._set_running_ui_state(True)
        self._start_run_clock()
        self.btn_resume_batch.setVisible(False)
        action_desc = "Reprise" if resume_incomplete else "Lancement"
        skip_msg = f" ({skipped_successful_count} tâche(s) déjà réussie(s) conservée(s))" if skipped_successful_count else ""
        self._log_formatted_line("INFO", f"🚀 {action_desc} du pipeline de traitement par lots : {len(tasks_payloads)} tâche(s) à exécuter{skip_msg}...")

        self.worker = BatchWorker(tasks=tasks_payloads, resume_incomplete=resume_incomplete)
        self.worker.task_started.connect(self._on_task_started)
        self.worker.task_progress.connect(self._on_task_progress)
        self.worker.task_completed.connect(self._on_task_completed)
        self.worker.task_failed.connect(self._on_task_failed)
        self.worker.log.connect(self._log_formatted_line)
        self.worker.batch_finished.connect(self._on_batch_finished)
        self.worker.cancelled.connect(self._on_batch_cancelled)
        if hasattr(self.worker, "task_review_ready"):
            self.worker.task_review_ready.connect(self._on_task_review_ready)
        if hasattr(self.worker, "task_accepted"):
            self.worker.task_accepted.connect(self._on_task_accepted)
        if hasattr(self.worker, "task_state_changed"):
            self.worker.task_state_changed.connect(self._on_task_state_changed)

        self.worker.start()

    @Slot()
    def _on_resume_batch(self) -> None:
        """Relance le traitement par lots uniquement sur les tâches non terminées ou en échec."""
        self._on_start_batch(resume_incomplete=True)

    def _update_resume_button_visibility(self) -> None:
        """Affiche le bouton de reprise si des tâches sont restées non terminées."""
        if not hasattr(self, "btn_resume_batch"):
            return
        has_incomplete = any(t.get("status") in ("Erreur", "Interrompu", "Échec", "En attente") for t in self.queue_tasks_data)
        has_finished = any(t.get("status") in ("Succès", "Acceptée") for t in self.queue_tasks_data)
        has_failures = any(t.get("status") in ("Erreur", "Interrompu", "Échec") for t in self.queue_tasks_data)
        self.btn_resume_batch.setVisible(has_incomplete and (has_finished or has_failures))

    @Slot()
    def _on_stop_batch(self) -> None:
        if self.worker and self.worker.isRunning():
            self._log_formatted_line("WARN", "Arrêt demandé par l'utilisateur. En attente de terminaison...")
            self.worker.cancel()

    @Slot(int, str)
    def _on_task_started(self, task_idx: int, doc_title: str) -> None:
        if 0 <= task_idx < len(self.queue_tasks_data):
            self.queue_tasks_data[task_idx]["status"] = "En cours"
            self.queue_widget.sync_started(task_idx)

        total = len(self.queue_tasks_data)
        self.card_status.val_lbl.setText(f"En cours ({task_idx + 1}/{total})")

    @Slot(int, int, str)
    def _on_task_progress(self, task_idx: int, progress_pct: int, step_detail: str) -> None:
        if 0 <= task_idx < len(self.queue_tasks_data):
            self.queue_tasks_data[task_idx]["progress_pct"] = progress_pct
            self.queue_widget.sync_progress(task_idx, progress_pct, step_detail)

        if self.start_timestamp > 0:
            elapsed = int(time.time() - self.start_timestamp)
            mins = elapsed // 60
            secs = elapsed % 60
            self.card_time.val_lbl.setText(f"{mins:02d}:{secs:02d}")

    @Slot(int, list, int)
    def _on_task_completed(self, task_idx: int, prepared_notes: list[dict[str, Any]], cards_count: int) -> None:
        if 0 <= task_idx < len(self.queue_tasks_data):
            task = self.queue_tasks_data[task_idx]
            task["progress_pct"] = 100
            task["cards_count"] = cards_count
            task["_staging_notes"] = prepared_notes
            self._prepared_notes_by_uid[self._task_uid(task)] = prepared_notes

            if task.get("_is_snapshot_task"):
                # Tâche de portée : le routage Succès/À réviser est piloté par le
                # signal task_state_changed émis par le worker (source autoritaire).
                return

            auto_val: bool = bool(task.get("auto_val", True))

            if auto_val:
                # Mode validation automatique : sauvegarde immédiate
                task["status"] = "Succès"
                deck_id = task["deck"].id if hasattr(task.get("deck"), "id") else 1
                model_id = task["note_type"].id if hasattr(task.get("note_type"), "id") else 1
                doc_id = task["doc"].id if hasattr(task.get("doc"), "id") else 0
                self._save_extracted_notes_to_db(prepared_notes, deck_id, model_id, doc_id)

                self.queue_widget.sync_completed(task_idx, "Succès", cards_count)
                self._total_cards_accumulated += cards_count
                self.card_cards.val_lbl.setText(f"{self._total_cards_accumulated} cartes")

            else:
                # Mode staging : mettre la tâche en revue, ne pas sauvegarder
                task["status"] = "À réviser"
                task["_staging_notes"] = prepared_notes
                self._prepared_notes_by_uid[self._task_uid(task)] = prepared_notes

                self.queue_widget.sync_completed(task_idx, "À réviser", cards_count)

                self._refresh_review_badge()
                self._log_formatted_line("INFO", f"Tâche #{task_idx + 1} prête pour revue ({cards_count} cartes).")

    @Slot(int, str)
    def _on_task_state_changed(self, task_idx: int, status_value: str) -> None:
        """Statut autoritaire d'une tâche de portée (BatchTaskSnapshot) signalé par le worker."""
        if not 0 <= task_idx < len(self.queue_tasks_data):
            return
        task = self.queue_tasks_data[task_idx]

        if status_value == BatchTaskStatus.RUNNING.value:
            task["status"] = "En cours"
            task["_attempt_count"] = int(task.get("_attempt_count", 0)) + 1
            self.queue_widget.sync_started(task_idx)
            return

        if status_value == BatchTaskStatus.FAILED.value:
            task["status"] = "Erreur"
            task["progress_pct"] = 100
            self.queue_widget.sync_failed(task_idx)
            return

        if status_value == BatchTaskStatus.CANCELLED.value:
            task["status"] = "Annulé"
            self.queue_widget.sync_completed(task_idx, "Annulé", int(task.get("cards_count", 0)))
            return

        if status_value == BatchTaskStatus.ACCEPTED.value:
            task["status"] = "Succès"
            cards_count = int(task.get("cards_count", 0))
            self.queue_widget.sync_completed(task_idx, "Succès", cards_count)
            notes = list(task.get("_staging_notes") or self._prepared_notes_by_uid.get(self._task_uid(task)) or [])
            if notes:
                deck_id = task["deck"].id if hasattr(task.get("deck"), "id") else 1
                model_id = task["note_type"].id if hasattr(task.get("note_type"), "id") else 1
                doc_id = task["doc"].id if hasattr(task.get("doc"), "id") else 0
                self._save_extracted_notes_to_db(notes, deck_id, model_id, doc_id)
            self._total_cards_accumulated += len(notes)
            self.card_cards.val_lbl.setText(f"{self._total_cards_accumulated} cartes")
            return

        if status_value == BatchTaskStatus.REVIEW.value:
            task["status"] = "À réviser"
            cards_count = int(task.get("cards_count", 0))
            self.queue_widget.sync_completed(task_idx, "À réviser", cards_count)
            self._refresh_review_badge()
            return

    @Slot(int, str)
    def _on_task_failed(self, task_idx: int, error_message: str) -> None:
        if 0 <= task_idx < len(self.queue_tasks_data):
            task = self.queue_tasks_data[task_idx]
            task["status"] = "Erreur"
            task["progress_pct"] = 100
            task["error_message"] = error_message
            self.queue_widget.sync_failed(task_idx)

    @Slot(int, int)
    def _on_task_accepted(self, task_idx: int, cards_count: int) -> None:
        """Mode validation automatique : la tâche est acceptée sans revue."""
        if 0 <= task_idx < len(self.queue_tasks_data):
            self.card_status.val_lbl.setText(f"Acceptée ({task_idx + 1})")

    def _default_queue_targets(self) -> dict[str, Any]:
        """Valeurs par défaut des nouvelles tâches de la file (deck, modèle, engine, pipeline, ...)."""
        engine = self.engine_combo.currentData() if self.engine_combo.count() else None
        pipeline = self.pipeline_combo.currentData() if self.pipeline_combo.count() else None
        return {
            "deck": self.current_deck,
            "deck_name": str(getattr(self.current_deck, "name", "Général")),
            "model": self.current_model,
            "model_name": str(getattr(self.current_model, "name", "Basique")),
            "engine": engine,
            "pipeline": pipeline,
            "pipeline_name": str(getattr(pipeline, "name", "Standard")),
            "use_vision": bool(self.cb_vision.isChecked()) if hasattr(self, "cb_vision") else False,
            "auto_val": bool(self.cb_autoval.isChecked()) if hasattr(self, "cb_autoval") else True,
            "temperature": self.slider_temp.value() / 10.0 if hasattr(self, "slider_temp") else 0.7,
            "max_tokens": self.slider_tokens.value() * 1024 if hasattr(self, "slider_tokens") else 16384,
        }

    def _slice_to_queue_task(self, doc: DocumentModel | None, s: SliceUnit) -> dict[str, Any] | None:
        """Construit un dict de tâche de file depuis un SliceUnit (mode Auto)."""
        if doc is None:
            return None
        defaults = self._default_queue_targets()
        return {
            "doc": doc,
            "doc_title": f"{doc.title} — {s.title}",
            "doc_content": s.content,
            "source_chunks": [s.as_dict()],
            "chunk_label": s.title,
            "chunk_index": s.index,
            "tokens_est": s.tokens_estimate or len(s.content.split()) * 4,
            "deck": defaults["deck"],
            "deck_name": defaults["deck_name"],
            "note_type": defaults["model"],
            "model_name": defaults["model_name"],
            "engine": defaults["engine"],
            "pipeline": defaults["pipeline"],
            "pipeline_name": defaults["pipeline_name"],
            "use_vision": defaults["use_vision"],
            "auto_val": defaults["auto_val"],
            "temperature": defaults["temperature"],
            "max_tokens": defaults["max_tokens"],
            "status": "En attente",
            "progress_pct": 0,
            "cards_count": 0,
            "pending_cards": [],
        }

    def _append_queue_tasks(self, task_dicts: list[dict[str, Any]]) -> None:
        """Ajoute les tâches composées (direct/auto) à la file d'attente."""
        added_count = 0
        for task in task_dicts:
            content = str(task.get("doc_content", "")).strip()
            if not content:
                continue
            task.setdefault("doc", None)
            task.setdefault("status", "En attente")
            task.setdefault("progress_pct", 0)
            task.setdefault("cards_count", 0)
            task.setdefault("pending_cards", [])
            task.setdefault("deck", self.current_deck)
            task.setdefault("note_type", self.current_model)
            task.setdefault("engine", self.engine_combo.currentData() if self.engine_combo.count() else None)
            task.setdefault("pipeline", self.pipeline_combo.currentData() if self.pipeline_combo.count() else None)
            task.setdefault("_queue_uid", str(uuid.uuid4()))
            task.setdefault("auto_val", True)
            self.queue_tasks_data.append(task)
            added_count += 1
        if added_count:
            self._update_queue_table()
            self._update_estimates_summary()
            show_toast(self, f"{added_count} tâche(s) ajoutée(s) à la Queue !")
            self._log_formatted_line("INFO", f"➕ {added_count} nouvelle(s) tâche(s) ajoutée(s) à la file d'attente.")

    def _chunk_to_queue_task(self, doc: DocumentModel, chunk: dict[str, Any]) -> dict[str, Any] | None:
        """Construit une tâche de file depuis une partie sélectionnée du document (mode Direct)."""
        if doc is None:
            return None
        defaults = self._default_queue_targets()
        chunk_content = str(chunk.get("content", "")).strip()
        if not chunk_content:
            return None
        chunk_title = str(chunk.get("title") or chunk.get("heading_path") or f"Section {chunk.get('index', 1) + 1}")
        return {
            "doc": doc,
            "doc_title": f"{doc.title} — {chunk_title}",
            "doc_content": chunk_content,
            "source_chunks": list(chunk["chunks"]) if chunk.get("chunks") else [chunk],
            "chunk_label": chunk_title,
            "chunk_index": int(chunk.get("index") or 0),
            "tokens_est": int(chunk.get("tokens") or len(chunk_content.split()) * 1.3),
            "deck": defaults["deck"],
            "deck_name": defaults["deck_name"],
            "note_type": defaults["model"],
            "model_name": defaults["model_name"],
            "engine": defaults["engine"],
            "pipeline": defaults["pipeline"],
            "pipeline_name": defaults["pipeline_name"],
            "use_vision": defaults["use_vision"],
            "auto_val": defaults["auto_val"],
            "temperature": defaults["temperature"],
            "max_tokens": defaults["max_tokens"],
            "status": "En attente",
            "progress_pct": 0,
            "cards_count": 0,
            "pending_cards": [],
        }

    def _scope_memory_for(self, doc: DocumentModel) -> dict[str, Any] | None:
        """Restitue la portée mémorisée d'un document pour préremplir le composer."""
        if getattr(doc, "id", None):
            return self._batch_scope_results.get(int(doc.id))
        return None

    def _snapshot_scope_for_task(self, task: dict[str, Any]) -> BatchScopeSnapshot | None:
        """Construit la portée figée (BatchScopeSnapshot) d'une tâche de file si le composer Direct l'a fournie."""
        doc = task.get("doc")
        if not doc or not getattr(doc, "id", None):
            return None
        scope_result = self._batch_scope_results.get(int(doc.id))
        if not scope_result:
            return None
        parts = scope_result.get("parts") or scope_result.get("chunks") or []
        if not parts:
            return None
        part_index = int(task.get("chunk_index", -1))
        part_label = str(task.get("chunk_label", ""))
        part = next((p for p in parts if p.get("index") == part_index), None)
        if part is None and part_label:
            part = next((p for p in parts if str(p.get("title") or p.get("heading_path") or "") == part_label), None)
        if part is None:
            return None
        content = str(part.get("content", "")).strip()
        if not content:
            return None
        page_number = part.get("page_number")
        heading_path = part.get("heading_path")
        scope_title = str(part.get("title") or heading_path or f"Section {part_index + 1}")
        block = BatchSourceBlock(
            kind="section",
            label=scope_title,
            content=content,
            ordinal=part_index,
            page_number=int(page_number) if page_number is not None else None,
            heading_path=str(heading_path) if heading_path else None,
            source_id=int(getattr(doc, "id", 0) or 0),
        )
        return BatchScopeSnapshot(
            document_id=int(doc.id),
            document_title=str(getattr(doc, "title", "")),
            selection_mode=str(scope_result.get("selection_mode", "sections")),
            blocks=(block,),
            scope_title=scope_title,
            range_str=str(part.get("heading_path") or part.get("title") or ""),
            content=content,
        )

    @Slot()
    def _on_open_batch_composer(self) -> None:
        """Ouvre la modale unique de composition du lot (document → parties → mode d'insertion)."""
        doc = self._last_composer_doc
        if doc is not None and getattr(doc, "id", None):
            try:
                doc = DocumentModel.get_by_id(doc.id)
            except Exception as err:
                logger.debug("Rechargement du document du composer ignoré : %s", err)
                doc = None

        dlg = BatchSliceComposerDialog(
            doc=doc,
            resolve_chunks=self._resolve_batch_chunks,
            scope_memory=self._scope_memory_for,
            task_from_chunk=self._chunk_to_queue_task,
            task_from_slice=lambda d, s: self._slice_to_queue_task(d, s),
            parent=self,
        )
        if dlg.exec():
            result = dlg.get_result()
            tasks = result.get("tasks") or []
            scope_result = result.get("scope_result")
            composed_doc = result.get("doc")
            if composed_doc is not None and getattr(composed_doc, "id", None):
                self._last_composer_doc = composed_doc
                if scope_result:
                    self._batch_scope_results[int(composed_doc.id)] = scope_result
            if tasks:
                self._append_queue_tasks(tasks)

    @Slot(int)
    def _on_retry_task(self, row_idx: int) -> None:
        """Relance une tâche en échec : remise en attente puis reprise du batch (max MAX_RETRY_ATTEMPTS tentatives)."""
        if 0 <= row_idx < len(self.queue_tasks_data):
            task = self.queue_tasks_data[row_idx]
            if task.get("_is_snapshot_task"):
                prev_attempts = task.get("_attempt_count", 0)
                if prev_attempts >= 3:
                    show_toast(self, "Tentative maximale de relance atteinte pour cette tâche.", is_error=True)
                    return
            task["status"] = "En attente"
            task["progress_pct"] = 0
            task["cards_count"] = 0
            task.pop("error_message", None)
            self._update_queue_table()
            self._log_formatted_line("INFO", f"Tâche #{row_idx + 1} relancée.")
            self._on_resume_batch()

    # ── Staging Panel Slots ──────────────────────────────────────────────

    def _task_index_by_uid(self, task_uid: str) -> int:
        """Résout une clé de rangée vers l'index courant de la file (-1 si inconnue)."""
        if not task_uid:
            return -1
        for idx, task in enumerate(self.queue_tasks_data):
            if self._task_uid(task) == task_uid:
                return idx
        return -1

    def _focus_review_tab(self) -> None:
        """Rend l'onglet « Revue » actif dans le terminal."""
        if 0 <= self._review_tab_idx < len(self.terminal_panel.tabs_bar.tabs):
            self.terminal_panel.set_active_tab(self._review_tab_idx)

    @Slot(int, list)
    def _on_task_review_ready(self, task_idx: int, prepared_notes: list[dict[str, Any]]) -> None:
        """Chargé par BatchWorker.task_review_ready : charge la revue sans écraser une revue active, et autofocus l'onglet si aucune revue n'est en cours."""
        if 0 <= task_idx < len(self.queue_tasks_data):
            task = self.queue_tasks_data[task_idx]
            uid = self._task_uid(task)
            self._prepared_notes_by_uid[uid] = prepared_notes
            task["_staging_notes"] = prepared_notes
            was_active = self.staging_panel._review_active
            self.staging_panel.load_task(task_idx, task, prepared_notes)
            if not was_active:
                self._focus_review_tab()

    def _staging_task_list(self) -> list[tuple[int, dict[str, Any], list[dict[str, Any]]]]:
        """Liste des tâches 'À réviser' avec leurs cartes, pour la revue agrégée du badge/volet."""
        result: list[tuple[int, dict[str, Any], list[dict[str, Any]]]] = []
        for task_idx, task in enumerate(self.queue_tasks_data):
            if task.get("status") != "À réviser":
                continue
            notes = self._prepared_notes_by_uid.get(self._task_uid(task)) or list(task.get("_staging_notes", []))
            if notes:
                result.append((task_idx, task, notes))
        return result

    def _advance_review(self) -> None:
        """Après une décision (accept/reject), avance vers la prochaine tâche 'À réviser' ou l'état vide."""
        remaining = self._staging_task_list()
        if not remaining:
            self.staging_panel.show_empty_state("Plus de tâche à réviser — la revue du lot est terminée.")
            return
        task_idx, task, notes = remaining[0]
        self.staging_panel.load_task(task_idx, task, notes, force=True)

    @Slot()
    def _on_open_staging_badge(self) -> None:
        """Clic sur le badge 'N à valider' : ouvre la revue de la première tâche en attente."""
        review_tasks = self._staging_task_list()
        if not review_tasks:
            show_toast(self, "Aucune carte en attente de validation.", is_error=False)
            return
        task_idx, task, notes = review_tasks[0]
        self.staging_panel.load_task(task_idx, task, notes, force=True)
        self._focus_review_tab()

    def _refresh_review_badge(self) -> None:
        staging_count = sum(1 for t in self.queue_tasks_data if t.get("status") == "À réviser")
        if hasattr(self.metrics_bar, "set_review_count"):
            self.metrics_bar.set_review_count(staging_count)
        if 0 <= self._review_tab_idx < len(self.terminal_panel.tabs_bar.tabs):
            self.terminal_panel.set_tab_title(self._review_tab_idx, f"Revue ({staging_count})" if staging_count else "Revue")

    @Slot(int)
    def _on_open_staging_for_task(self, task_idx: int) -> None:
        """Ouvre la revue d'une tâche (via 'Examiner', clic simple ou relecture) et focus l'onglet."""
        if 0 <= task_idx < len(self.queue_tasks_data):
            task = self.queue_tasks_data[task_idx]
            notes = self._prepared_notes_by_uid.get(self._task_uid(task)) or list(task.get("_staging_notes", []))
            if notes:
                self.staging_panel.load_task(task_idx, task, notes, force=True)
                self._focus_review_tab()
            else:
                show_toast(self, "Aucune carte en attente de revue pour cette tâche.", is_error=True)

    @Slot(str, list)
    def _on_staging_accepted(self, task_uid: str, accepted_cards: list[dict[str, Any]]) -> None:
        """Appelé quand le staging panel valide des cartes : résout la clé de rangée puis met à jour le statut."""
        task_idx = self._task_index_by_uid(task_uid)
        if task_idx < 0:
            logger.warning("Clé de rangée inconnue à l'acceptation (%s) ; signal ignoré.", task_uid)
            return
        task = self.queue_tasks_data[task_idx]
        task["status"] = "Acceptée"
        task["cards_count"] = len(accepted_cards)
        self._total_cards_accumulated += len(accepted_cards)
        self.card_cards.val_lbl.setText(f"{self._total_cards_accumulated} cartes")

        self.queue_widget.sync_completed(task_idx, "Acceptée", len(accepted_cards))

        self._log_formatted_line("SUCCESS", f"Tâche #{task_idx + 1} validée : {len(accepted_cards)} carte(s) enregistrée(s).")
        self._advance_review()
        self._refresh_review_badge()

    @Slot(str)
    def _on_staging_rejected(self, task_uid: str) -> None:
        """Appelé quand le staging panel rejette une tranche : résout la clé de rangée puis met à jour le statut."""
        task_idx = self._task_index_by_uid(task_uid)
        if task_idx < 0:
            logger.warning("Clé de rangée inconnue au rejet (%s) ; signal ignoré.", task_uid)
            return
        task = self.queue_tasks_data[task_idx]
        task["status"] = "Rejetée"
        task["cards_count"] = 0

        self.queue_widget.sync_completed(task_idx, "Rejetée", 0)

        self._log_formatted_line("WARN", f"Tâche #{task_idx + 1} rejetée par l'utilisateur.")
        self._advance_review()
        self._refresh_review_badge()

    def accept_batch_task(self, task_idx: int, accepted_cards: list[dict[str, Any]] | None = None) -> bool:
        """Persist the reviewed cards for one new scope-based queue row."""
        if not 0 <= task_idx < len(self.queue_tasks_data):
            return False
        task = self.queue_tasks_data[task_idx]
        pending = accepted_cards if accepted_cards is not None else list(task.get("pending_cards", []))
        original_count = len(pending)
        if not task.get("_is_snapshot_task") or not pending:
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
        if not task.get("_is_snapshot_task"):
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
        self._stop_run_clock()
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
        self._update_resume_button_visibility()

    @Slot()
    def _on_batch_cancelled(self) -> None:
        self._stop_run_clock()
        self._set_running_ui_state(False)
        self.card_status.val_lbl.setText("Interrompu")
        self.card_status.val_lbl.setStyleSheet(f"color: {DesignTokens.COLOR_YELLOW}; font-size: 15px; font-weight: bold; border: none; font-family: '{DesignTokens.FONT_CODE}';")
        self._log_formatted_line("WARN", "Traitement par lots interrompu par l'utilisateur.")
        show_toast(self, "Batch interrompu par l'utilisateur.", is_error=False)

        self._update_queue_table()
        self._update_resume_button_visibility()

    @Slot(str)
    def _on_batch_error(self, error_msg: str) -> None:
        self.card_status.val_lbl.setText("Erreur")
        self.card_status.val_lbl.setStyleSheet(f"color: {DesignTokens.COLOR_RED}; font-size: 16px; font-weight: bold; border: none; font-family: '{DesignTokens.FONT_CODE}';")
        self._log_formatted_line("ERROR", error_msg)
        log_and_notify_error(error_msg, context="Exécution du pipeline", parent=self, title="Erreur Pipeline")

    def refresh_theme(self, profile: Any) -> None:
        if hasattr(self, "metrics_bar"):
            self.metrics_bar.refresh_theme(profile)

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

        if hasattr(self, "queue_widget"):
            self.queue_widget.refresh_theme(profile)

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

        for cell in self.queue_widget.cell_widgets_map.values():
            if hasattr(cell, "refresh_theme"):
                cell.refresh_theme(profile)

        from ankiforge.ui.components.panels import IdePanel

        for panel in self.findChildren(IdePanel):
            if hasattr(panel, "refresh_theme"):
                panel.refresh_theme(profile)


BatchTab = BatchView

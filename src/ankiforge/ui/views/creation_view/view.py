import json
import logging
from typing import Any, cast

from peewee import fn
from PySide6.QtCore import QEvent, Qt, QThreadPool, Signal, Slot
from PySide6.QtGui import QCloseEvent, QKeyEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QSplitter,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import (
    DeckModel,
    DocumentChunkModel,
    NoteChunkLinkModel,
    NoteTypeModel,
)
from ankiforge.repositories import (
    DeckRepository,
    DocumentRepository,
    NoteRepository,
    PersonaRepository,
    PipelineRepository,
)
from ankiforge.services.ai.orchestrator import PipelineOrchestrator
from ankiforge.services.ai.state import PipelineRunState
from ankiforge.services.ai.utils import extract_cards_from_data
from ankiforge.services.cards.note_manager import NoteManager
from ankiforge.ui.components import (
    Badge,
    DangerButton,
    IconButton,
    IdePanel,
    PrimaryButton,
    SecondaryButton,
    StatusBadge,
    StyledComboBox,
    StyledLineEdit,
    StyledTableWidget,
)
from ankiforge.ui.components.deck_select_window import DeckSelectWindow
from ankiforge.ui.dialogs.human_validation_dialog import HumanValidationDialog
from ankiforge.ui.dialogs.selection_dialog import MultiSelectionDialog
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.viewmodels import CreationViewModel
from ankiforge.ui.views.creation_view.dialogs import CardEditDialog
from ankiforge.ui.views.creation_view.utils import parse_page_ranges
from ankiforge.ui.views.creation_view.widgets import (
    CreationHubWidget,
    DocumentEditorWidget,
    FlashcardPreview,
    VisionCard,
)
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.event_bus import (
    CardCreatedEvent,
    NoteCreatedEvent,
    event_bus,
)
from ankiforge.utils.icon_loader import load_phosphor_icon
from ankiforge.utils.logger import log_and_notify_error

logger = logging.getLogger(__name__)


class CreationView(QWidget):
    """
    Studio de Création AnkiForge.
    Signal request_navigation(str) pour basculer vers d'autres vues (documents, pipelines, settings).
    """

    request_navigation = Signal(str, object)

    def __init__(self, ai_manager: Any = None, profile_name: str = "default", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ai_manager = ai_manager
        self.profile_name = profile_name
        self.note_repo = NoteRepository()
        self.deck_repo = DeckRepository()
        self.pipeline_repo = PipelineRepository()
        self.doc_repo = DocumentRepository()
        self.persona_repo = PersonaRepository()
        self.view_model = CreationViewModel(
            note_repo=self.note_repo,
            deck_repo=self.deck_repo,
            pipeline_repo=self.pipeline_repo,
            doc_repo=self.doc_repo,
            bus=event_bus,
            parent=self,
        )
        self.generated_cards: list[dict[str, Any]] = []
        self.current_preview_index = 0
        self.orchestrator: PipelineOrchestrator | None = None
        self.current_deck: DeckModel | None = None
        self.current_model: NoteTypeModel | None = None
        self.selected_models: list[NoteTypeModel] = []
        self.current_source_title: str = "Saisie Libre"
        self.decks_cache: list[DeckModel] = []
        self._deck_modal: DeckSelectWindow | None = None
        self.models_cache: list[NoteTypeModel] = []
        self.open_editors: dict[str, DocumentEditorWidget] = {}
        self.thread_pool = QThreadPool(self)

        self._setup_ui()
        self._connect_signals()
        self.refresh_data()

    def _navigate(self, view_id: str, data: dict | None = None) -> None:
        self.request_navigation.emit(view_id, data)

    def _setup_ui(self) -> None:
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(self.main_splitter)

        # --- COL 1: Left Tool Window (Explorateur + Config IA) ---
        self.config_panel = IdePanel(detachable=True)
        self.config_panel.setMinimumWidth(350)
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
        config_scroll = QScrollArea()
        config_scroll.setWidgetResizable(True)
        config_scroll.setFrameShape(QFrame.Shape.NoFrame)
        config_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        config_scroll.setStyleSheet("""
            QScrollArea {
                background: transparent;
                border: none;
            }
        """)

        config_content = QWidget()
        config_content.setStyleSheet("background: transparent;")
        config_layout = QVBoxLayout(config_content)
        config_layout.setContentsMargins(8, 8, 8, 8)
        config_layout.setSpacing(12)

        # --- Section 1: Cibles Anki ---
        target_card = QFrame()
        target_card.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)
        target_layout = QVBoxLayout(target_card)
        target_layout.setContentsMargins(10, 10, 10, 10)
        target_layout.setSpacing(8)

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
            f"text-align: left; padding: 7px 10px; border-radius: 6px; border: 1px solid {DesignTokens.BORDER_COLOR}; background: {DesignTokens.BG_PANEL}; font-weight: 500;"
        )
        target_layout.addWidget(self.btn_select_deck)

        self.btn_select_model = SecondaryButton("Sélectionner un modèle...")
        self.btn_select_model.setIcon(load_phosphor_icon("ph.file-code", color=DesignTokens.TEXT_MUTED))
        self.btn_select_model.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_select_model.setStyleSheet(
            f"text-align: left; padding: 7px 10px; border-radius: 6px; border: 1px solid {DesignTokens.BORDER_COLOR}; background: {DesignTokens.BG_PANEL}; font-weight: 500;"
        )
        target_layout.addWidget(self.btn_select_model)
        config_layout.addWidget(target_card)

        # --- Section 2: Orchestration IA ---
        ai_card = QFrame()
        ai_card.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)
        ai_layout = QVBoxLayout(ai_card)
        ai_layout.setContentsMargins(10, 10, 10, 10)
        ai_layout.setSpacing(8)

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

        self.vision_card = VisionCard()
        self.vision_card.setObjectName("visionCard")
        self.vision_card.setStyleSheet(f"""
            QFrame#visionCard {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
            }}
            QFrame#visionCard:hover {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        self.vision_card.setCursor(Qt.CursorShape.PointingHandCursor)
        vision_layout = QVBoxLayout(self.vision_card)
        vision_layout.setContentsMargins(10, 8, 10, 8)
        vision_layout.setSpacing(4)

        vision_top = QHBoxLayout()
        self.lbl_vision_icon = QLabel()
        self.lbl_vision_icon.setPixmap(load_phosphor_icon("ph.eye-closed", color=DesignTokens.TEXT_MUTED).pixmap(16, 16))
        self.lbl_vision_title = QLabel("Vision (PDF)")
        self.lbl_vision_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: 600; font-size: 12px; border: none; background: transparent;")

        self.vision_badge = Badge("OFF", variant="neutral")

        vision_top.addWidget(self.lbl_vision_icon)
        vision_top.addWidget(self.lbl_vision_title)
        vision_top.addStretch()
        vision_top.addWidget(self.vision_badge)
        vision_layout.addLayout(vision_top)

        self.lbl_vision_desc = QLabel("Extraction multimodale des schémas & figures.")
        self.lbl_vision_desc.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; border: none; background: transparent;")
        self.lbl_vision_desc.setWordWrap(True)
        vision_layout.addWidget(self.lbl_vision_desc)

        self.vision_cb = QCheckBox()
        self.vision_cb.hide()
        vision_layout.addWidget(self.vision_cb)

        self.vision_card.hide()
        ai_layout.addWidget(self.vision_card)
        config_layout.addWidget(ai_card)

        # --- Section 3: Portée du Document ---
        self.scope_card = QFrame()
        self.scope_card.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)
        scope_layout = QVBoxLayout(self.scope_card)
        scope_layout.setContentsMargins(10, 10, 10, 10)
        scope_layout.setSpacing(8)

        scope_top = QHBoxLayout()
        scope_top.setContentsMargins(0, 0, 0, 0)
        scope_top.setSpacing(6)
        scope_ico = QLabel()
        scope_ico.setPixmap(load_phosphor_icon("ph.sliders", color=DesignTokens.COLOR_BLUE).pixmap(14, 14))
        scope_ico.setStyleSheet("border: none; background: transparent;")
        lbl_scope = QLabel("PORTÉE DU DOCUMENT")
        lbl_scope.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-weight: 700; font-size: 11px; letter-spacing: 0.5px; border: none; background: transparent;")

        self.scope_badge = Badge("10 pages", variant="neutral")

        scope_top.addWidget(scope_ico)
        scope_top.addWidget(lbl_scope)
        scope_top.addStretch()
        scope_top.addWidget(self.scope_badge)
        scope_layout.addLayout(scope_top)

        preset_row = QHBoxLayout()
        preset_row.setSpacing(4)

        preset_btn_style = f"""
            QPushButton {{
                background-color: {DesignTokens.BG_PANEL};
                color: {DesignTokens.TEXT_SECONDARY};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 10px;
                padding: 2px 7px;
                font-size: 10px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {DesignTokens.BG_HOVER};
                color: {DesignTokens.TEXT_PRIMARY};
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """

        self.btn_preset_all = QPushButton("Tout le doc")
        self.btn_preset_all.setStyleSheet(preset_btn_style)
        self.btn_preset_all.setCursor(Qt.CursorShape.PointingHandCursor)

        self.btn_preset_page = QPushButton("Page 1")
        self.btn_preset_page.setStyleSheet(preset_btn_style)
        self.btn_preset_page.setCursor(Qt.CursorShape.PointingHandCursor)

        self.btn_preset_range = QPushButton("1 – 10")
        self.btn_preset_range.setStyleSheet(preset_btn_style)
        self.btn_preset_range.setCursor(Qt.CursorShape.PointingHandCursor)

        preset_row.addWidget(self.btn_preset_all, 1)
        preset_row.addWidget(self.btn_preset_page, 1)
        preset_row.addWidget(self.btn_preset_range, 1)
        scope_layout.addLayout(preset_row)

        input_container = QFrame()
        input_container.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
            QFrame:focus-within {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        input_layout = QHBoxLayout(input_container)
        input_layout.setContentsMargins(6, 2, 4, 2)
        input_layout.setSpacing(4)

        self.input_page_scope = StyledLineEdit()
        self.input_page_scope.setText("1-10")
        self.input_page_scope.setPlaceholderText("ex: 1-5, 8, 12-15")
        self.input_page_scope.setStyleSheet("background: transparent; border: none; font-size: 11px; font-weight: 600;")
        input_layout.addWidget(self.input_page_scope, 1)

        btn_stepper_style = f"""
            QPushButton {{
                background: transparent;
                border: none;
                border-radius: 3px;
                padding: 2px;
            }}
            QPushButton:hover {{
                background: {DesignTokens.BG_HOVER};
            }}
        """

        self.btn_scope_minus = IconButton("ph.minus", "Réduire l'étendue", 16)
        self.btn_scope_minus.setStyleSheet(btn_stepper_style)
        self.btn_scope_plus = IconButton("ph.plus", "Élargir l'étendue", 16)
        self.btn_scope_plus.setStyleSheet(btn_stepper_style)

        input_layout.addWidget(self.btn_scope_minus)
        input_layout.addWidget(self.btn_scope_plus)
        scope_layout.addWidget(input_container)

        self.lbl_scope_stats = QLabel("~1 200 mots • ~6 cartes estimées")
        self.lbl_scope_stats.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; border: none; background: transparent;")
        scope_layout.addWidget(self.lbl_scope_stats)

        self.spin_page_start = QSpinBox(self)
        self.spin_page_start.hide()
        self.spin_page_end = QSpinBox(self)
        self.spin_page_end.hide()
        self.spin_page_start.setValue(1)
        self.spin_page_end.setValue(10)

        self.scope_card.hide()
        config_layout.addWidget(self.scope_card)

        # Paramètres Avancés
        self.btn_toggle_advanced = QPushButton()
        self.btn_toggle_advanced.setStyleSheet("background: transparent; border: none; text-align: left; padding: 4px 0;")
        self.btn_toggle_advanced.setCursor(Qt.CursorShape.PointingHandCursor)

        advanced_header = QHBoxLayout(self.btn_toggle_advanced)
        advanced_header.setContentsMargins(0, 0, 0, 0)
        advanced_lbl = QLabel("Paramètres Avancés")
        advanced_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11px; font-weight: 500; background: transparent; border: none;")

        self.advanced_icon = QLabel()
        self.advanced_icon.setPixmap(load_phosphor_icon("ph.caret-right", color=DesignTokens.TEXT_MUTED).pixmap(12, 12))
        self.advanced_icon.setStyleSheet("background: transparent; border: none;")

        advanced_header.addWidget(advanced_lbl)
        advanced_header.addStretch()
        advanced_header.addWidget(self.advanced_icon)

        config_layout.addWidget(self.btn_toggle_advanced)

        self.advanced_container = QFrame()
        self.advanced_container.setObjectName("advancedContainer")
        self.advanced_container.setVisible(False)
        self.advanced_container.setStyleSheet(f"""
            QFrame#advancedContainer {{
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
        temp_lbl = QLabel("Température")
        temp_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px; border: none; background: transparent;")
        self.val_temp_lbl = QLabel("0.7")
        self.val_temp_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-family: {DesignTokens.FONT_CODE}; font-size: 11px; border: none; background: transparent;")
        temp_header.addWidget(temp_lbl)
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
        tokens_lbl = QLabel("Max Tokens")
        tokens_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px; border: none; background: transparent;")
        self.val_tokens_lbl = QLabel("4096")
        self.val_tokens_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-family: {DesignTokens.FONT_CODE}; font-size: 11px; border: none; background: transparent;")
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

        self.btn_generate_cards = QPushButton(self)
        self.btn_generate_cards.hide()

        config_scroll.setWidget(config_content)
        self.config_panel.add_tab("Explorateur", explorer_content, "ph.files", closable=False)
        self.config_panel.add_tab("Config IA", config_scroll, "ph.cpu", closable=False)
        self.config_panel.set_active_tab(0)

        self.main_splitter.addWidget(self.config_panel)

        # --- COL 2: Source + Results ---
        self.center_splitter = QSplitter(Qt.Orientation.Vertical)
        self.main_splitter.addWidget(self.center_splitter)

        source_container = QWidget()
        source_layout = QVBoxLayout(source_container)
        source_layout.setContentsMargins(0, 0, 0, 0)

        self.source_panel = IdePanel(detachable=True, tab_variant="document")
        source_layout.addWidget(self.source_panel)

        self.center_splitter.addWidget(source_container)

        self.results_panel = IdePanel(detachable=True)

        cartes_content = QWidget()
        cartes_layout = QVBoxLayout(cartes_content)
        cartes_layout.setContentsMargins(0, 0, 0, 0)

        self.results_splitter = QSplitter(Qt.Orientation.Horizontal)

        table_container = QWidget()
        table_layout = QVBoxLayout(table_container)
        table_layout.setContentsMargins(12, 12, 12, 12)
        table_layout.setSpacing(8)
        table_container.setStyleSheet(f"border-right: 1px solid {DesignTokens.BORDER_COLOR};")

        self.results_table = StyledTableWidget(["Recto", "Verso", "Statut"])
        self.results_table.setSelectionBehavior(StyledTableWidget.SelectionBehavior.SelectRows)
        self.results_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.results_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.results_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.results_table.horizontalHeader().setMinimumSectionSize(125)
        self.results_table.itemSelectionChanged.connect(self._on_table_selection_changed)
        self.results_table.itemChanged.connect(self._on_cell_edited)
        self.results_table.installEventFilter(self)
        table_layout.addWidget(self.results_table, 1)

        self.results_splitter.addWidget(table_container)

        self.preview_widget = FlashcardPreview()
        self.results_splitter.addWidget(self.preview_widget)

        cartes_layout.addWidget(self.results_splitter, 1)

        main_bot_toolbar = QHBoxLayout()
        main_bot_toolbar.setContentsMargins(12, 0, 12, 12)

        self.btn_save_anki = PrimaryButton("Enregistrer dans la Forge (0)")
        self.btn_save_anki.setIcon(load_phosphor_icon("ph.floppy-disk", color="white"))
        self.btn_save_anki.setEnabled(False)
        self.btn_save_anki.setToolTip("Enregistrer les cartes validées dans votre collection AnkiForge (Ctrl+S)")
        main_bot_toolbar.addWidget(self.btn_save_anki)

        main_bot_toolbar.addStretch()

        self.btn_rejeter = DangerButton("Rejeter", ghost=True)
        self.btn_rejeter.setIcon(load_phosphor_icon("ph.trash", color=DesignTokens.COLOR_RED))
        self.btn_rejeter.setToolTip("Rejeter la carte active et passer à la suivante (Raccourci: Suppr ou R)")

        self.btn_editer = SecondaryButton("Éditer")
        self.btn_editer.setIcon(load_phosphor_icon("ph.pencil-simple", color=DesignTokens.TEXT_PRIMARY))
        self.btn_editer.setToolTip("Modifier le texte de la carte (Raccourci: E)")

        self.btn_valider = PrimaryButton("Garder")
        self.btn_valider.setIcon(load_phosphor_icon("ph.check", color="white"))
        self.btn_valider.setToolTip("Garder la carte active et passer à la suivante (Raccourci: Espace ou V)")

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
        self.results_panel.set_active_tab(0)

        self.center_splitter.addWidget(self.results_panel)
        self.results_panel.hide()
        self.main_splitter.setSizes([360, 920])

        self.hub_widget = CreationHubWidget(parent=self)
        self.hub_widget.open_free_text_requested.connect(lambda: self._open_document_tab("Saisie Libre"))
        self.hub_widget.open_documents_requested.connect(self._on_hub_open_documents)
        self.source_panel.register_tab("Démarrage", self.hub_widget, "ph.sparkle", closable=False, icon_color=DesignTokens.ACCENT_PRIMARY)
        self._update_vision_ui(False)

    def _connect_signals(self) -> None:
        self.btn_new_free_input.clicked.connect(lambda: self._open_document_tab("Nouvelle Saisie"))
        self.file_tree.itemDoubleClicked.connect(self._on_explorer_item_double_clicked)
        self.btn_generate_cards.clicked.connect(self._on_generate_from_tree)

        self.btn_select_deck.clicked.connect(self._on_click_select_deck)
        self.btn_select_model.clicked.connect(self._on_click_select_model)

        self.btn_preset_all.clicked.connect(self._on_preset_all)
        self.btn_preset_page.clicked.connect(self._on_preset_single_page)
        self.btn_preset_range.clicked.connect(lambda: self.input_page_scope.setText("1-10"))
        self.btn_scope_minus.clicked.connect(self._on_scope_step_minus)
        self.btn_scope_plus.clicked.connect(self._on_scope_step_plus)
        self.input_page_scope.textChanged.connect(self._on_page_scope_changed)

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

    @Slot()
    def _on_hub_open_documents(self) -> None:
        self.config_panel.set_active_tab(0)
        show_toast(self, "Sélectionnez ou double-cliquez sur un document à gauche.")

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
            self.lbl_vision_icon.setPixmap(load_phosphor_icon("ph.eye", color=DesignTokens.COLOR_YELLOW).pixmap(16, 16))
            self.vision_badge.setText("ON")
            self.vision_badge.set_variant("warning")
            self.vision_card.setStyleSheet(f"""
                QFrame#visionCard {{
                    background-color: {DesignTokens.BG_ACTIVE};
                    border: 1px solid {DesignTokens.COLOR_YELLOW};
                    border-radius: {DesignTokens.RADIUS_SM}px;
                }}
            """)
        else:
            self.lbl_vision_icon.setPixmap(load_phosphor_icon("ph.eye-closed", color=DesignTokens.TEXT_MUTED).pixmap(16, 16))
            self.vision_badge.setText("OFF")
            self.vision_badge.set_variant("neutral")
            self.vision_card.setStyleSheet(f"""
                QFrame#visionCard {{
                    background-color: {DesignTokens.BG_INPUT};
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    border-radius: {DesignTokens.RADIUS_SM}px;
                }}
                QFrame#visionCard:hover {{
                    border-color: {DesignTokens.ACCENT_PRIMARY};
                }}
            """)

    def refresh_data(self) -> None:
        """Recharge les données dynamiques depuis Peewee DB (Decks, NoteTypes, Engines, Pipelines, Docs)."""
        try:
            decks = self.deck_repo.get_all_decks()
            if not decks:
                self.deck_repo.create_deck(name="Général")
                decks = self.deck_repo.get_all_decks()
            self.decks_cache = decks
            if self.current_deck is None and self.decks_cache:
                self._set_current_deck(self.decks_cache[0])

            note_types = self.note_repo.get_all_note_types()
            if not note_types:
                note_types = [
                    NoteTypeModel(name="Basique (Recto/Verso)", fields_schema="[]"),
                    NoteTypeModel(name="Texte à trous (Cloze)", fields_schema="[]"),
                ]
            self.models_cache = note_types
            if not self.selected_models and self.models_cache:
                self.selected_models = list(self.models_cache)
            if self.current_model is None and self.models_cache:
                self._set_current_model(self.models_cache[0])
            else:
                self._update_selected_models_display()

            self.engine_combo.blockSignals(True)
            self.engine_combo.clear()
            engines = self.persona_repo.get_all_llm_configs()
            if not engines:
                self.persona_repo.create_llm_config(
                    display_name="GPT-4o (OpenAI)",
                    provider="openai",
                    model_id="gpt-4o",
                    context_limit=128000,
                )
                self.persona_repo.create_llm_config(
                    display_name="Claude 3.5 Sonnet (Anthropic)",
                    provider="anthropic",
                    model_id="claude-3-5-sonnet-20240620",
                    context_limit=200000,
                )
                engines = self.persona_repo.get_all_llm_configs()

            for eg in engines:
                display_name = getattr(eg, "display_name", getattr(eg, "name", str(eg)))
                self.engine_combo.addItem(load_phosphor_icon("ph.cpu", color=DesignTokens.ACCENT_PRIMARY), display_name, userData=eg)
            self.btn_no_engine_help.hide()
            self.engine_combo.blockSignals(False)

            self.pipeline_combo.blockSignals(True)
            self.pipeline_combo.clear()
            pipelines = self.pipeline_repo.get_all_pipelines()
            if not pipelines:
                p1 = self.pipeline_repo.create_pipeline(
                    name="Excellence Math/Info (Archiviste + Linter)",
                    description="Pipeline haute-fidélité pour les cours scientifiques.",
                )
                pipelines = [p1]

            for pipe in pipelines:
                self.pipeline_combo.addItem(load_phosphor_icon("ph.tree-structure", color=DesignTokens.COLOR_BLUE), pipe.name, userData=pipe)
            self.btn_no_pipeline_help.hide()
            self.pipeline_combo.blockSignals(False)

            self.file_tree.clear()

            folders = self.doc_repo.get_all_folders()
            docs = self.doc_repo.get_all_documents()

            folder_items: dict[int, QTreeWidgetItem] = {}
            for folder in folders:
                f_item = QTreeWidgetItem(self.file_tree)
                f_item.setText(0, folder.name)
                f_item.setIcon(0, load_phosphor_icon("ph.folder", color=DesignTokens.ACCENT_PRIMARY, weight="fill"))
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

                    title_lower = doc.title.lower()
                    is_album = getattr(doc, "file_type", "") == "album"
                    is_pdf = getattr(doc, "file_type", "") == "pdf"
                    has_content = bool(doc.content and doc.content.strip())

                    if is_album:
                        p_count = getattr(doc, "total_pages", 0) or 0
                        item.setIcon(0, load_phosphor_icon("ph.images", color=DesignTokens.COLOR_PURPLE, weight="fill"))
                        item.setText(0, f"{doc.title} ({p_count}p)")
                    elif is_pdf:
                        if has_content:
                            item.setIcon(0, load_phosphor_icon("ph.file-pdf", color=DesignTokens.COLOR_RED, weight="fill"))
                        else:
                            item.setIcon(0, load_phosphor_icon("ph.file-pdf", color=DesignTokens.TEXT_MUTED))
                            item.setText(0, f"{doc.title} (Non extrait)")
                    elif getattr(doc, "file_type", "") == "epub" or title_lower.endswith(".epub"):
                        item.setIcon(0, load_phosphor_icon("ph.book-open", color=DesignTokens.COLOR_PURPLE, weight="fill"))
                    elif getattr(doc, "file_type", "") == "pptx" or title_lower.endswith(".pptx"):
                        item.setIcon(0, load_phosphor_icon("ph.presentation", color=DesignTokens.COLOR_YELLOW, weight="fill"))
                    elif getattr(doc, "file_type", "") in ("audio", "mp3", "m4a", "wav", "ogg", "flac", "aac") or title_lower.endswith((".mp3", ".m4a", ".wav", ".ogg", ".flac", ".aac")):
                        item.setIcon(0, load_phosphor_icon("ph.waveform", color=DesignTokens.COLOR_GREEN, weight="fill"))
                    elif getattr(doc, "file_type", "") in ("md", "txt", "json", "csv") or title_lower.endswith((".md", ".txt", ".json", ".csv")):
                        item.setIcon(0, load_phosphor_icon("ph.file-code", color=DesignTokens.COLOR_YELLOW, weight="fill"))
                    else:
                        item.setIcon(0, load_phosphor_icon("ph.file-text", color=DesignTokens.COLOR_GREEN, weight="fill"))

                    item.setData(0, Qt.ItemDataRole.UserRole, doc)

            self._on_model_changed()

        except Exception as e:
            logger.warning("Erreur lors de la mise à jour des combos creation_view: %s", e, exc_info=True)

    _FINAL_STATUSES = frozenset({"Enregistrée", "Refusée"})

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
                log_and_notify_error(e, context="Création de paquet", parent=self, title="Erreur")

    @Slot()
    def _open_settings_modal(self) -> None:
        from ankiforge.ui.widgets.settings_modal import SettingsModal

        modal = SettingsModal(ai_manager=self.ai_manager, parent=self)
        modal.exec()

    def _open_document_tab(self, title: str, content: str = "", doc_model: Any | None = None) -> None:
        base_title = title
        counter = 1
        while title in self.open_editors:
            title = f"{base_title} {counter}"
            counter += 1

        editor_widget = DocumentEditorWidget(content, source_title=title, doc_model=doc_model, parent=self)
        editor_widget.generate_requested.connect(self._on_generate)
        editor_widget.cancel_requested.connect(self._on_cancel_generation)

        self.open_editors[title] = editor_widget
        icon = "ph.text-t"
        icon_color = DesignTokens.TEXT_SECONDARY

        if doc_model:
            title_lower = title.lower()
            is_album = getattr(doc_model, "file_type", "") == "album"
            if is_album:
                icon = "ph.images"
                icon_color = DesignTokens.COLOR_PURPLE
            elif title_lower.endswith(".pdf"):
                icon = "ph.file-pdf"
                icon_color = DesignTokens.COLOR_RED
            elif title_lower.endswith((".md", ".txt", ".json", ".csv")):
                icon = "ph.file-code"
                icon_color = DesignTokens.COLOR_BLUE
            else:
                icon = "ph.file-text"
                icon_color = DesignTokens.COLOR_BLUE

        self.source_panel.register_tab(title, editor_widget, icon, closable=True, icon_color=icon_color)

        if doc_model is not None:
            self.scope_card.show()
            is_pdf = getattr(doc_model, "file_type", "") == "pdf"
            is_album = getattr(doc_model, "file_type", "") == "album"
            self.vision_card.setVisible(is_pdf or is_album)

            if is_album:
                total_pages = int(getattr(doc_model, "total_pages", 0) or 1)
            else:
                max_page_chunk = DocumentChunkModel.select(fn.MAX(DocumentChunkModel.page_number)).where(DocumentChunkModel.document == doc_model).scalar()
                total_pages = int(max_page_chunk) if max_page_chunk else 10
            self._current_doc_total_pages = total_pages
            self.btn_preset_all.setText(f"Tout ({total_pages}p)")
            self.btn_preset_range.setText(f"1 – {min(10, total_pages)}")
            self.input_page_scope.blockSignals(True)
            self.input_page_scope.setText(f"1-{min(10, total_pages)}")
            self.input_page_scope.blockSignals(False)
            self._on_page_scope_changed()
        else:
            self.scope_card.hide()
            self.vision_card.hide()

        self.config_panel.set_active_tab(1)

    @Slot(QTreeWidgetItem, int)
    def _on_explorer_item_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        doc = item.data(0, Qt.ItemDataRole.UserRole)
        if doc and hasattr(doc, "content"):
            title = doc.title if hasattr(doc, "title") else "Document"
            is_pdf = getattr(doc, "file_type", "") == "pdf"
            is_album = getattr(doc, "file_type", "") == "album"
            has_content = bool(doc.content and doc.content.strip())

            if is_pdf and not has_content:
                show_toast(self, "Ce PDF n'a pas encore été extrait. Vous ne pouvez pas l'ouvrir en texte.", is_error=True)
                return

            album_content = doc.content or ""
            if is_album:
                from ankiforge.database.models import DocumentPageModel

                pages = list(DocumentPageModel.select().where(DocumentPageModel.document == doc).order_by(DocumentPageModel.page_number))
                parts = [f"### Page {p.page_number}\n\n{p.ocr_text}" for p in pages if p.ocr_text and p.ocr_text.strip()]
                if parts:
                    album_content = "\n\n".join(parts)

            if title in self.open_editors:
                try:
                    _ = self.open_editors[title].parent()
                    self.source_panel.open_tab(title)
                    self.config_panel.set_active_tab(1)
                except RuntimeError:
                    self.open_editors.pop(title, None)
                    self._open_document_tab(title, album_content, doc)
            else:
                self._open_document_tab(title, album_content, doc)

    def _set_all_generation_states(self, is_generating: bool) -> None:
        for editor in self.open_editors.values():
            editor.set_generation_state(is_generating)

    @Slot()
    def _on_preset_all(self) -> None:
        doc_total = getattr(self, "_current_doc_total_pages", 10) or 10
        self.input_page_scope.setText(f"1-{doc_total}")

    @Slot()
    def _on_preset_single_page(self) -> None:
        self.input_page_scope.setText("1")

    @Slot()
    def _on_scope_step_minus(self) -> None:
        pages = parse_page_ranges(self.input_page_scope.text())
        if len(pages) > 1:
            new_end = pages[-2]
            self.input_page_scope.setText(f"{pages[0]}-{new_end}" if new_end > pages[0] else str(pages[0]))

    @Slot()
    def _on_scope_step_plus(self) -> None:
        pages = parse_page_ranges(self.input_page_scope.text())
        if pages:
            doc_total = getattr(self, "_current_doc_total_pages", 9999) or 9999
            new_end = min(doc_total, pages[-1] + 1)
            self.input_page_scope.setText(f"{pages[0]}-{new_end}")

    @Slot()
    def _on_page_scope_changed(self) -> None:
        scope_text = self.input_page_scope.text().strip()
        doc_total = getattr(self, "_current_doc_total_pages", 9999) or 9999
        pages = parse_page_ranges(scope_text, max_pages=doc_total)

        if not pages:
            self.scope_badge.setText("0 page")
            self.scope_badge.set_variant("danger")
            self.lbl_scope_stats.setText("Aucune page sélectionnée")
            return

        count = len(pages)
        if count == 1:
            self.scope_badge.setText("1 page")
            self.scope_badge.set_variant("neutral")
        else:
            self.scope_badge.setText(f"{count} pages")
            self.scope_badge.set_variant("success")

        approx_words = count * 280
        approx_cards = max(1, count * 2)
        self.lbl_scope_stats.setText(f"~{approx_words:,} mots • ~{approx_cards} cartes estimées".replace(",", " "))

        start = pages[0]
        end = pages[-1]

        self.spin_page_start.blockSignals(True)
        self.spin_page_end.blockSignals(True)
        self.spin_page_start.setValue(start)
        self.spin_page_end.setValue(end)
        self.spin_page_start.blockSignals(False)
        self.spin_page_end.blockSignals(False)

        selected_items = self.file_tree.selectedItems()
        if not selected_items:
            return

        doc = selected_items[0].data(0, Qt.ItemDataRole.UserRole)
        if not doc or not hasattr(doc, "title"):
            return

        editor = self.open_editors.get(doc.title)
        if not editor:
            return

        is_album = getattr(doc, "file_type", "") == "album"
        if is_album:
            from ankiforge.database.models import DocumentPageModel

            pages_models = list(DocumentPageModel.select().where((DocumentPageModel.document == doc) & DocumentPageModel.page_number.in_(pages)).order_by(DocumentPageModel.page_number))
            content_parts = [f"### Page {p.page_number}\n\n{p.ocr_text}" for p in pages_models if p.ocr_text and p.ocr_text.strip()]
            if not content_parts:
                visual_chunks = list(DocumentChunkModel.select().where((DocumentChunkModel.document == doc) & DocumentChunkModel.page_number.in_(pages)).order_by(DocumentChunkModel.page_number))
                if visual_chunks:
                    content_parts = [vc.content for vc in visual_chunks if vc.content]
            msg = f"_Aucune transcription ou analyse visuelle trouvée pour les pages d'album {scope_text}_" if not content_parts else "\n\n".join(content_parts)
            editor.set_content(msg)
            return

        has_pages = DocumentChunkModel.select().where((DocumentChunkModel.document == doc) & DocumentChunkModel.page_number.is_null(False)).exists()

        if has_pages:
            chunks = list(
                DocumentChunkModel.select()
                .where((DocumentChunkModel.document == doc) & DocumentChunkModel.page_number.in_(pages))
                .order_by(DocumentChunkModel.page_number, DocumentChunkModel.chunk_index)
            )
        else:
            chunks = list(
                DocumentChunkModel.select()
                .where((DocumentChunkModel.document == doc) & (DocumentChunkModel.chunk_index >= start - 1) & (DocumentChunkModel.chunk_index <= end - 1))
                .order_by(DocumentChunkModel.chunk_index)
            )

        if not chunks:
            msg = f"_Aucun contenu trouvé pour les pages {scope_text}_" if has_pages else f"_Aucun contenu trouvé pour les sections {scope_text}_"
            editor.set_content(msg)
            return

        content = "\n\n".join([c.content for c in chunks])
        editor.set_content(content)
        editor.set_pdf_scope(pages)

    @Slot()
    def _on_generate_from_tree(self) -> None:
        selected_items = self.file_tree.selectedItems()
        if not selected_items:
            show_toast(self, "Veuillez sélectionner un document dans l'arborescence.", is_error=True)
            return

        doc = selected_items[0].data(0, Qt.ItemDataRole.UserRole)
        if not doc or not hasattr(doc, "content"):
            show_toast(self, "Veuillez sélectionner un document valide.", is_error=True)
            return

        is_album = getattr(doc, "file_type", "") == "album"
        editor = self.open_editors.get(doc.title)
        content_to_use = editor.get_text() if editor else doc.content

        if is_album and (not content_to_use or not content_to_use.strip()):
            from ankiforge.database.models import DocumentPageModel

            pages = list(DocumentPageModel.select().where(DocumentPageModel.document == doc).order_by(DocumentPageModel.page_number))
            parts = [f"### Page {p.page_number}\n\n{p.ocr_text}" for p in pages if p.ocr_text and p.ocr_text.strip()]
            if parts:
                content_to_use = "\n\n".join(parts)
            elif doc.content and doc.content.strip():
                content_to_use = doc.content
            elif pages:
                show_toast(self, "Cet album n'a pas encore été analysé par RAG Visuel ou Vision IA.", is_error=True)
                return
            else:
                show_toast(self, "Cet album ne contient aucune page.", is_error=True)
                return
        elif not content_to_use or not content_to_use.strip():
            show_toast(self, "Ce document est vide ou n'a pas encore été extrait.", is_error=True)
            return

        self._on_generate(content_to_use, doc.title)

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
        self._deck_modal.deck_selected.connect(self._on_deck_selected_from_modal)
        self._deck_modal.show()

    @Slot(int, str)
    def _on_deck_selected_from_modal(self, deck_id: int, deck_name: str) -> None:
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
        initial = self.selected_models or ([self.current_model] if self.current_model else [])
        dialog = MultiSelectionDialog(
            title="Sélectionner les modèles de cartes autorisés pour l'IA",
            items=self.models_cache,
            display_func=lambda m: m.name,
            initial_selected=initial,
            parent=self,
        )
        if dialog.exec():
            selected = dialog.get_selected_items()
            if selected:
                self.selected_models = selected
                self.current_model = selected[0]
                self._update_selected_models_display()
                self._on_model_changed()

    def _update_selected_models_display(self) -> None:
        if not self.selected_models:
            if self.current_model:
                self.selected_models = [self.current_model]
            elif self.models_cache:
                self.selected_models = [self.models_cache[0]]
                self.current_model = self.models_cache[0]

        if len(self.selected_models) == 1:
            name = getattr(self.selected_models[0], "name", str(self.selected_models[0]))
            self.btn_select_model.setText(name)
        elif len(self.selected_models) > 1:
            first_name = getattr(self.selected_models[0], "name", str(self.selected_models[0]))
            self.btn_select_model.setText(f"{first_name} (+{len(self.selected_models) - 1})")
        else:
            self.btn_select_model.setText("Sélectionner un modèle...")

    def _set_current_model(self, model: Any) -> None:
        self.current_model = model
        if model and model not in self.selected_models:
            self.selected_models = [model]
        self._update_selected_models_display()
        self._on_model_changed()

    @Slot()
    def _on_model_changed(self) -> None:
        headers = ["Modèle", "Recto / Texte", "Verso / Détails", "Statut"]
        self.results_table.blockSignals(True)
        self.results_table.clear()
        self.results_table.setColumnCount(len(headers))
        self.results_table.setHorizontalHeaderLabels(headers)
        self.results_table.setRowCount(0)
        self.results_table.blockSignals(False)

    @Slot(str, str)
    def _on_generate(self, text_source: str = "", source_title: str = "Saisie Libre") -> None:
        self.current_source_title = source_title

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
        fields = json.loads(nt_schema) if nt_schema else ["Front", "Back"]

        pipe_id = selected_pipeline.id if selected_pipeline and hasattr(selected_pipeline, "id") else None

        provider = None
        if self.ai_manager and hasattr(self.ai_manager, "create_provider_from_config"):
            try:
                provider = self.ai_manager.create_provider_from_config(selected_engine)
            except Exception as e:
                logger.warning("Impossible de créer le provider depuis la config: %s", e)

        initial_state = PipelineRunState(initial_prompt=text_source[:120])
        initial_state.set_variable("text_source", text_source)
        initial_state.set_variable("fields", fields)
        first_field = fields[0] if len(fields) > 0 else "Front"
        second_field = fields[1] if len(fields) > 1 else "Back"
        fields_str = ", ".join([f'"{f}"' for f in fields])
        initial_state.set_variable("first_field", first_field)
        initial_state.set_variable("second_field", second_field)
        initial_state.set_variable("fields_str", fields_str)
        initial_state.set_variable("note_type_id", nt_id)
        initial_state.set_variable("note_type_fields_schema", nt_schema)
        initial_state.set_variable("selected_models", self.selected_models or ([selected_nt] if selected_nt else []))

        self._set_all_generation_states(True)
        self.results_panel.show()
        self.center_splitter.setSizes([450, 350])

        self.orchestrator = PipelineOrchestrator(
            pipeline_id=pipe_id,
            initial_state=initial_state,
            ai_provider=provider,
        )
        self.orchestrator.setAutoDelete(False)
        self.orchestrator.signals.step_started.connect(self._on_orchestrator_step_started)
        self.orchestrator.signals.step_progress.connect(self._on_orchestrator_step_progress)
        self.orchestrator.signals.step_completed.connect(self._on_orchestrator_step_completed)
        self.orchestrator.signals.human_validation_required.connect(self._on_human_validation)
        self.orchestrator.signals.pipeline_finished.connect(self._on_orchestrator_finished)
        self.orchestrator.signals.error_occurred.connect(self._on_generation_error)
        self.orchestrator.signals.cancelled.connect(self._on_generation_cancelled)

        self.thread_pool.start(self.orchestrator)

    @Slot(int, str)
    def _on_orchestrator_step_started(self, step_order: int, desc: str) -> None:
        logger.info("[Orchestrateur] Démarrage étape %d : %s", step_order, desc)
        active_editor = self.open_editors.get(getattr(self, "current_source_title", ""))
        if active_editor:
            active_editor.raw_editor.setPlaceholderText(f"⏳ Étape {step_order}: {desc}...")

    @Slot(int, int, str)
    def _on_orchestrator_step_progress(self, current: int, total: int, detail: str) -> None:
        logger.info("[Orchestrateur] Progression (%d/%d) : %s", current, total, detail)
        active_editor = self.open_editors.get(getattr(self, "current_source_title", ""))
        if active_editor:
            active_editor.raw_editor.setPlaceholderText(f"⏳ {detail} ({current}/{total})...")

    @Slot(int, object)
    def _on_orchestrator_step_completed(self, step_order: int, state: PipelineRunState) -> None:
        logger.info("[Orchestrateur] Étape %d terminée avec succès.", step_order)

    @Slot(object)
    def _on_human_validation(self, state: PipelineRunState) -> None:
        logger.info("[Orchestrateur] PAUSE INTERACTIVE : Validation Humaine Requise.")
        dialog = HumanValidationDialog(state, self)
        res = dialog.exec()
        if res == QDialog.DialogCode.Accepted:
            show_toast(self, "Plan validé ! Poursuite du pipeline...", is_error=False)
            if self.orchestrator:
                self.orchestrator.resume(state)
        else:
            show_toast(self, "Génération interrompue par l'utilisateur.", is_error=False)
            if self.orchestrator:
                self.orchestrator.cancel()

    @Slot(object)
    def _on_orchestrator_finished(self, state: PipelineRunState) -> None:
        self._set_all_generation_states(False)

        cards_raw = state.get_variable("generated_cards") or state.get_variable("map_reduce_results") or state.get_variable("last_output") or []
        cards = extract_cards_from_data(cards_raw)

        selected_nt = self.current_model
        default_model_name = selected_nt.name if selected_nt else "Basique"

        cleaned_notes: list[dict[str, Any]] = []
        if isinstance(cards, list):
            for item in cards:
                if isinstance(item, dict):
                    card_model_name = item.get("model") or item.get("note_type") or default_model_name
                    target_nt = None
                    if self.models_cache:
                        for m in self.models_cache:
                            if m.name.lower().strip() == str(card_model_name).lower().strip():
                                target_nt = m
                                break
                    if not target_nt:
                        target_nt = selected_nt

                    m_schema = str(target_nt.fields_schema) if target_nt and hasattr(target_nt, "fields_schema") and target_nt.fields_schema else '["Front", "Back"]'
                    try:
                        m_fields = json.loads(m_schema) if m_schema else ["Front", "Back"]
                    except Exception:
                        m_fields = ["Front", "Back"]

                    lower_item = {str(k).lower().strip(): v for k, v in item.items()}
                    raw_values = [v for k, v in item.items() if str(k).lower() not in ("model", "note_type", "status", "chunk_id")]

                    note_dict: dict[str, Any] = {
                        "model": target_nt.name if target_nt else default_model_name,
                        "status": item.get("status", "À valider"),
                    }
                    if "chunk_id" in item:
                        note_dict["chunk_id"] = item["chunk_id"]

                    for i, field_name in enumerate(m_fields):
                        f_lower = field_name.lower().strip()
                        if f_lower in lower_item:
                            val = lower_item[f_lower]
                        elif i < len(raw_values):
                            val = raw_values[i]
                        else:
                            val = ""

                        val = "<br>".join([str(v) for v in val]) if isinstance(val, list) else str(val) if val is not None else ""
                        note_dict[field_name] = val

                    for k, v in item.items():
                        if k not in note_dict and str(k).lower() not in ("status",):
                            note_dict[k] = v

                    cleaned_notes.append(note_dict)

        if cleaned_notes:
            self._on_generation_finished(cleaned_notes)
        else:
            show_toast(self, "Pipeline terminé (aucune carte générée).", is_error=False)
        logger.info("[Orchestrateur] Fin du Pipeline. %d cartes obtenues.", len(cleaned_notes))

    @Slot(list)
    def _on_generation_finished(self, cards: list[dict[str, Any]]) -> None:
        self._set_all_generation_states(False)
        self.generated_cards = cards
        self.current_preview_index = 0

        self._populate_results_table()
        self._update_card_preview()
        self._refresh_save_button()
        show_toast(self, f"{len(cards)} cartes générées avec succès !")

    @Slot(str)
    def _on_generation_error(self, err_msg: str) -> None:
        self._set_all_generation_states(False)
        self.results_panel.show()
        self.err_lbl.setText(f"Erreur de génération : {err_msg}")
        self.results_panel.set_tab_title(1, "Journal des Erreurs (1)")
        self.results_panel.set_active_tab(1)
        show_toast(self, f"Erreur : {err_msg}", is_error=True)

    @Slot()
    def _on_generation_cancelled(self) -> None:
        self._set_all_generation_states(False)
        show_toast(self, "Génération annulée.", is_error=False)

    def eventFilter(self, obj: Any, event: Any) -> bool:
        if obj == self.results_table and event.type() == QEvent.Type.KeyPress:
            key_event = cast(QKeyEvent, event)
            key = key_event.key()
            if key in (Qt.Key.Key_Space, Qt.Key.Key_V):
                self._on_validate_card()
                return True
            elif key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace, Qt.Key.Key_R):
                self._on_reject_card()
                return True
            elif key == Qt.Key.Key_E:
                self._on_edit_card()
                return True
        return super().eventFilter(obj, event)

    @Slot()
    def _on_cancel_generation(self) -> None:
        if self.orchestrator:
            self.orchestrator.cancel()
            self._set_all_generation_states(False)
            show_toast(self, "Pipeline annulé.", is_error=False)

    def _populate_results_table(self) -> None:
        saved_index = self.current_preview_index

        if len(self.generated_cards) > 0:
            self.results_panel.show()
            self.results_panel.set_active_tab(0)

        self.results_table.blockSignals(True)
        self.results_table.setRowCount(len(self.generated_cards))
        self.results_panel.set_tab_title(0, f"Cartes Générées ({len(self.generated_cards)})")

        headers = ["Modèle", "Recto / Texte Principal", "Verso / Détails", "Statut"]
        self.results_table.setColumnCount(len(headers))
        self.results_table.setHorizontalHeaderLabels(headers)

        _STATUS_META = {
            "Acceptée": ("Validée", "ph.check-circle", "success"),
            "Validée": ("Validée", "ph.check-circle", "success"),
            "Refusée": ("Refusée", "ph.x-circle", "danger"),
            "À valider": ("À valider", "ph.hourglass-simple", "warning"),
            "En attente": ("En attente", "ph.hourglass-simple", "warning"),
            "Enregistrée": ("Enregistrée", "ph.floppy-disk", "info"),
        }

        for row, card in enumerate(self.generated_cards):
            card["status"] = card.get("status", "À valider")
            card_model_name = card.get("model") or (self.current_model.name if self.current_model else "Basique")
            card["model"] = card_model_name

            front_text = card.get("Front") or card.get("Recto") or card.get("Texte") or card.get("Théorème") or ""
            back_text = card.get("Back") or card.get("Verso") or card.get("Remarques extra") or card.get("Démonstration") or ""
            status_text = card["status"]

            model_combo = StyledComboBox()
            model_combo.setFixedHeight(26)
            for m in self.models_cache:
                model_combo.addItem(m.name, m)
            idx = model_combo.findText(card_model_name)
            if idx >= 0:
                model_combo.setCurrentIndex(idx)

            def make_combo_handler(r=row, combo=model_combo):
                def handler(index: int):
                    new_model_name = combo.currentText()
                    if 0 <= r < len(self.generated_cards):
                        self.generated_cards[r]["model"] = new_model_name
                        if self.current_preview_index == r:
                            self._update_card_preview()

                return handler

            model_combo.currentIndexChanged.connect(make_combo_handler(row, model_combo))
            self.results_table.setCellWidget(row, 0, model_combo)

            front_item = QTableWidgetItem(str(front_text))
            front_item.setToolTip(str(front_text))
            self.results_table.setItem(row, 1, front_item)

            back_item = QTableWidgetItem(str(back_text))
            back_item.setToolTip(str(back_text))
            self.results_table.setItem(row, 2, back_item)

            label, icon_name, variant = _STATUS_META.get(status_text, (status_text, "ph.hourglass-simple", "warning"))

            badge_container = QWidget()
            badge_layout = QHBoxLayout(badge_container)
            badge_layout.setContentsMargins(6, 2, 6, 2)
            badge_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge = StatusBadge(label, icon_name=icon_name, variant=variant)
            badge_layout.addWidget(badge)

            self.results_table.setItem(row, 3, QTableWidgetItem())
            self.results_table.setCellWidget(row, 3, badge_container)
            self.results_table.setRowHeight(row, 38)

        self.results_table.blockSignals(False)

        if self.generated_cards:
            target = max(0, min(saved_index, len(self.generated_cards) - 1))
            self.results_table.selectRow(target)

        self._refresh_save_button()

    def _update_card_preview(self) -> None:
        total = len(self.generated_cards)
        if total == 0:
            self.preview_widget.lbl_counter.setText("0 / 0")
            return

        self.current_preview_index = max(0, min(self.current_preview_index, total - 1))
        self.preview_widget.lbl_counter.setText(f"{self.current_preview_index + 1} / {total}")

        card = self.generated_cards[self.current_preview_index]
        card_model_name = card.get("model") or card.get("note_type")
        selected_nt = None
        if card_model_name and self.models_cache:
            for m in self.models_cache:
                if m.name.lower().strip() == str(card_model_name).lower().strip():
                    selected_nt = m
                    break
        if not selected_nt:
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
            card = self.generated_cards[row]
            card_model_name = card.get("model", "")
            if "cloze" in card_model_name.lower():
                if col == 1:
                    card["Texte"] = text
                elif col == 2:
                    card["Remarques extra"] = text
            else:
                if col == 1:
                    card["Front"] = text
                    card["Recto"] = text
                elif col == 2:
                    card["Back"] = text
                    card["Verso"] = text
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

    def _all_cards_processed(self) -> bool:
        if not self.generated_cards:
            return False
        return all(card.get("status") in self._FINAL_STATUSES for card in self.generated_cards)

    def _count_validated(self) -> int:
        return sum(1 for card in self.generated_cards if card.get("status") == "Validée")

    def _count_by_status(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for card in self.generated_cards:
            s = card.get("status", "À valider")
            counts[s] = counts.get(s, 0) + 1
        return counts

    def is_dirty(self) -> bool:
        return any(card.get("status") in ("Validée", "À valider", "En attente") for card in self.generated_cards)

    def _refresh_save_button(self) -> None:
        validated_count = self._count_validated()
        total_count = len(self.generated_cards)
        if total_count > 0:
            self.btn_save_anki.setText(f"Enregistrer dans la Forge ({validated_count}/{total_count})")
            self.btn_save_anki.setEnabled(True)
        else:
            self.btn_save_anki.setText("Enregistrer dans la Forge (0)")
            self.btn_save_anki.setEnabled(False)

    @Slot()
    def _on_validate_card(self) -> None:
        if not self.generated_cards or not (0 <= self.current_preview_index < len(self.generated_cards)):
            return
        next_index = self.current_preview_index + 1
        self.generated_cards[self.current_preview_index]["status"] = "Validée"
        self._populate_results_table()
        show_toast(self, "✅ Carte acceptée !")

        if next_index < len(self.generated_cards):
            self.current_preview_index = next_index
            self.results_table.selectRow(self.current_preview_index)
            self._update_card_preview()
        else:
            self.results_table.selectRow(self.current_preview_index)
            self._update_card_preview()
            show_toast(self, "✅ Toutes les cartes ont été passées en revue !", is_error=False)

    @Slot()
    def _on_edit_card(self) -> None:
        if not self.generated_cards or not (0 <= self.current_preview_index < len(self.generated_cards)):
            return

        card = self.generated_cards[self.current_preview_index]
        previous_status = card.get("status", "À valider")

        dlg = CardEditDialog(
            front=card.get("Front", card.get("Recto", "")),
            back=card.get("Back", card.get("Verso", "")),
            parent=self,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_front, new_back = dlg.get_data()
            card["Front"] = new_front
            card["Back"] = new_back
            card["status"] = previous_status
            self._populate_results_table()
            self._update_card_preview()
            show_toast(self, "✏️ Carte modifiée en mémoire.")

    @Slot()
    def _on_reject_card(self) -> None:
        if self.generated_cards and 0 <= self.current_preview_index < len(self.generated_cards):
            next_index = self.current_preview_index + 1
            card = self.generated_cards[self.current_preview_index]
            card["status"] = "Refusée"
            self._populate_results_table()
            show_toast(self, f"❌ Carte '{card.get('Front', '')[:20]}...' marquée Refusée.")

            if next_index < len(self.generated_cards):
                self.current_preview_index = next_index
                self.results_table.selectRow(self.current_preview_index)
                self._update_card_preview()
            else:
                self.results_table.selectRow(self.current_preview_index)
                self._update_card_preview()
                show_toast(self, "Toutes les cartes ont été passées en revue.", is_error=False)

    @Slot()
    def _on_save_anki(self) -> None:
        if not self.generated_cards:
            show_toast(self, "Aucune carte générée à enregistrer.", is_error=True)
            return

        pending_cards = [c for c in self.generated_cards if c.get("status") in ("À valider", "En attente")]
        validated_cards = [c for c in self.generated_cards if c.get("status") == "Validée"]

        if pending_cards:
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Icon.Question)
            msg_box.setWindowTitle("Enregistrement des Cartes")
            msg_box.setText(f"Il reste <b>{len(pending_cards)} carte(s)</b> en attente de décision.")
            msg_box.setInformativeText("Souhaitez-vous tout valider automatiquement ou enregistrer uniquement les cartes déjà marquées 'Validée' ?")

            btn_accept_all = msg_box.addButton(
                f"Tout Valider et Enregistrer ({len(validated_cards) + len(pending_cards)})",
                QMessageBox.ButtonRole.AcceptRole,
            )
            btn_save_validated = msg_box.addButton(
                f"Enregistrer Validées Uniquement ({len(validated_cards)})",
                QMessageBox.ButtonRole.ActionRole,
            )
            _ = msg_box.addButton("Continuer la Revue", QMessageBox.ButtonRole.RejectRole)

            msg_box.exec()
            clicked_btn = msg_box.clickedButton()

            if clicked_btn == btn_accept_all:
                for c in self.generated_cards:
                    if c.get("status") in ("À valider", "En attente"):
                        c["status"] = "Validée"
                validated_cards = [c for c in self.generated_cards if c.get("status") == "Validée"]
            elif clicked_btn == btn_save_validated:
                if not validated_cards:
                    show_toast(self, "Aucune carte n'a encore été marquée 'Validée'. Utilisez 'Garder' ou validez tout.", is_error=True)
                    return
            else:
                return

        if not validated_cards:
            show_toast(self, "Aucune carte 'Validée' à enregistrer. Utilisez 'Garder' pour valider des cartes.", is_error=True)
            return

        selected_nt = self.current_model
        if not selected_nt:
            show_toast(self, "Aucun modèle de carte sélectionné.", is_error=True)
            return

        deck_data = self.current_deck
        deck_name = deck_data.name if deck_data and hasattr(deck_data, "name") else "Général"

        saved_count = 0
        try:
            for card in validated_cards:
                card_model_name = card.get("model") or card.get("note_type")
                target_nt = None
                if card_model_name and self.models_cache:
                    for m in self.models_cache:
                        if m.name.lower().strip() == str(card_model_name).lower().strip():
                            target_nt = m
                            break
                if not target_nt:
                    target_nt = selected_nt

                try:
                    schema = json.loads(str(target_nt.fields_schema)) if target_nt.fields_schema else ["Front", "Back"]
                except Exception:
                    schema = ["Front", "Back"]

                fields = {}
                for f_name in schema:
                    val = card.get(f_name)
                    if val is None:
                        if f_name.lower() in ("front", "recto"):
                            val = card.get("Front") or card.get("Recto") or card.get("Texte") or ""
                        elif f_name.lower() in ("back", "verso"):
                            val = card.get("Back") or card.get("Verso") or card.get("Remarques extra") or ""
                        elif f_name.lower() in ("texte",):
                            val = card.get("Texte") or card.get("Front") or ""
                        elif f_name.lower() in ("remarques extra", "remarque", "extra"):
                            val = card.get("Remarques extra") or card.get("Back") or ""
                        else:
                            val = ""
                    fields[f_name] = str(val) if val is not None else ""

                tags = ["ankiforge_generated"]
                if getattr(self, "current_source_title", None) and self.current_source_title != "Saisie Libre":
                    clean_title = self.current_source_title.replace(" ", "_").replace("-", "_").lower()
                    if clean_title.endswith((".pdf", ".md", ".txt")):
                        clean_title = clean_title.rsplit(".", 1)[0]
                    tags.append(f"source:{clean_title}")

                deck_obj = self.deck_repo.get_or_create_deck(name=deck_name)
                note = NoteManager.create_note(
                    note_type=target_nt,
                    deck=deck_obj,
                    content_dict=fields,
                    tags=tags,
                    source="ai",
                )

                if note:
                    event_bus.publish(NoteCreatedEvent(note_id=note.id, deck_name=deck_name, tags=tags))
                    for c in self.note_repo.get_cards_by_note(note.id):
                        event_bus.publish(CardCreatedEvent(card_id=c.id, note_id=note.id, deck_name=deck_name))

                    target_chunk_id = card.get("chunk_id") or getattr(self, "current_source_chunk_id", None)
                    if target_chunk_id:
                        try:
                            NoteChunkLinkModel.get_or_create(note=note, chunk_id=int(target_chunk_id))
                        except Exception as e:
                            logger.warning("Erreur lors de la création du lien NoteChunkLink: %s", e)

                card["status"] = "Enregistrée"
                saved_count += 1

            self._populate_results_table()
            show_toast(self, f"💾 {saved_count} carte(s) enregistrée(s) dans la Forge !", is_error=False)
            self._check_completion()

        except Exception as e:
            log_and_notify_error(e, context="Enregistrement dans Anki", parent=self, title="Erreur de Sauvegarde")

    def _check_completion(self) -> None:
        if not self._all_cards_processed():
            counts = self._count_by_status()
            pending = counts.get("À valider", 0) + counts.get("En attente", 0)
            if pending:
                show_toast(
                    self,
                    f"⏳ {pending} carte(s) restante(s) à traiter (Garder ou Rejeter).",
                    is_error=False,
                )
            return

        counts = self._count_by_status()
        saved = counts.get("Enregistrée", 0)
        refused = counts.get("Refusée", 0)
        show_toast(
            self,
            f"🎉 Session terminée : {saved} carte(s) enregistrée(s), {refused} refusée(s).",
            is_error=False,
        )

    def closeEvent(self, event: QCloseEvent) -> None:
        import os

        if os.environ.get("QT_QPA_PLATFORM") == "offscreen" or not self.isVisible() or getattr(self, "_skip_close_dialog", False):
            event.accept()
            return

        if self.is_dirty():
            unsaved_count = sum(1 for c in self.generated_cards if c.get("status") in ("Validée", "À valider", "En attente"))
            reply = QMessageBox.question(
                self,
                "Quitter le Studio de Création ?",
                f"{unsaved_count} carte(s) générée(s) n'ont pas encore été enregistrées dans la Forge.\n\nVoulez-vous vraiment fermer sans enregistrer ?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                event.ignore()
                return
        event.accept()

    def refresh_theme(self, profile: Any) -> None:
        if hasattr(self, "preview_widget") and hasattr(self.preview_widget, "card_preview_widget"):
            self.preview_widget.card_preview_widget.refresh_theme(profile)

        if hasattr(self, "config_panel"):
            self.config_panel.setStyleSheet(f"border-right: 1px solid {profile.border_color};")

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

        if hasattr(self, "vision_card"):
            self.vision_card.setStyleSheet(f"""
                QFrame#visionCard {{
                    background-color: {profile.bg_input};
                    border: 1px solid {profile.border_color};
                    border-radius: 6px;
                }}
                QFrame#visionCard:hover {{
                    border-color: {profile.accent_primary};
                }}
            """)
        if hasattr(self, "lbl_vision_title"):
            self.lbl_vision_title.setStyleSheet(f"color: {profile.text_primary}; font-weight: 600; font-size: 12px;")
        if hasattr(self, "lbl_vision_desc"):
            self.lbl_vision_desc.setStyleSheet(f"color: {profile.text_muted}; font-size: 11px;")
        if hasattr(self, "lbl_vision_icon"):
            self.lbl_vision_icon.setPixmap(load_phosphor_icon("ph.eye-closed", color=profile.text_muted).pixmap(16, 16))

        if hasattr(self, "pages_input_frame"):
            self.pages_input_frame.setStyleSheet(f"""
                QFrame {{
                    background-color: {profile.bg_input};
                    border: 1px solid {profile.border_color};
                    border-radius: {profile.radius_md}px;
                    padding: 2px 6px;
                }}
                QSpinBox {{
                    background: transparent;
                    border: none;
                    color: {profile.text_primary};
                    font-weight: bold;
                }}
                QSpinBox::up-button, QSpinBox::down-button {{
                    width: 0px;
                }}
            """)

        if hasattr(self, "advanced_container"):
            self.advanced_container.setStyleSheet(f"""
                background-color: {profile.bg_input};
                border-radius: {profile.radius_sm}px;
                border: 1px solid {profile.border_color};
            """)

        from ankiforge.ui.components.panels import IdePanel

        for panel in self.findChildren(IdePanel):
            if hasattr(panel, "refresh_theme"):
                panel.refresh_theme(profile)


CreationTab = CreationView

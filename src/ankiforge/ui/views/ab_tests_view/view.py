import json
import logging
import time
import uuid
from typing import Any

from PySide6.QtCore import QSize, Qt, QThreadPool, Slot
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QSlider,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    LLMConfigModel,
    NoteModel,
    NoteTypeModel,
    PersonaModel,
    PipelineModel,
    PipelineStepModel,
    db,
)
from ankiforge.services.ai.orchestrator import PipelineOrchestrator
from ankiforge.services.ai.state import PipelineRunState
from ankiforge.services.ai.utils import extract_cards_from_data
from ankiforge.ui.components import (
    IconButton,
    IdePanel,
    PrimaryButton,
    SecondaryButton,
    StyledComboBox,
    StyledTextEdit,
)
from ankiforge.ui.theme import DesignTokens, apply_shadow
from ankiforge.ui.views.ab_tests_view.constants import PRESET_SAMPLES
from ankiforge.ui.views.ab_tests_view.widgets import (
    BranchKpiWidget,
    SubTabButton,
    TagPillButton,
)
from ankiforge.ui.widgets.card_preview_widget import CardPreviewWidget
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class ABTestsView(QWidget):
    """
    Vue Laboratoire A/B — Comparateur haute précision de Moteurs, Prompts et Pipelines DAG.
    """

    def __init__(self, ai_manager: Any | None = None, profile_name: str = "default", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ai_manager = ai_manager
        self.profile_name = profile_name

        self.cards_a: list[dict[str, Any]] = []
        self.index_a: int = 0

        self.cards_b: list[dict[str, Any]] = []
        self.index_b: int = 0

        self.orchestrator_a: PipelineOrchestrator | None = None
        self.orchestrator_b: PipelineOrchestrator | None = None
        self._start_time_a: float = 0.0
        self._start_time_b: float = 0.0
        self._completed_a: bool = False
        self._completed_b: bool = False
        self._source_collapsed: bool = False
        self._adv_collapsed: bool = True

        self.source_text_edit: StyledTextEdit = StyledTextEdit()

        self._setup_ui()
        self._connect_signals()
        self.refresh_data()
        self._insert_mock_initial_data()

    def _build_advanced_settings(self) -> tuple[QWidget, QSlider, QSlider]:
        """Génère un widget compact pour les réglages de température et tokens."""
        adv_widget = QWidget()
        adv_layout = QHBoxLayout(adv_widget)
        adv_layout.setContentsMargins(8, 4, 8, 4)
        adv_layout.setSpacing(14)

        lbl_temp = QLabel("Température :")
        lbl_temp.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")

        temp_slider = QSlider(Qt.Orientation.Horizontal)
        temp_slider.setRange(0, 200)
        temp_slider.setValue(70)
        temp_slider.setFixedWidth(110)

        slider_style = f"""
            QSlider::groove:horizontal {{
                border: 1px solid {DesignTokens.BORDER_COLOR};
                height: 4px;
                background: {DesignTokens.BG_MAIN};
                margin: 0px 0;
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: {DesignTokens.ACCENT_PRIMARY};
                border: 1px solid {DesignTokens.ACCENT_PRIMARY};
                width: 12px;
                height: 12px;
                margin: -4px 0;
                border-radius: 6px;
            }}
            QSlider::sub-page:horizontal {{
                background: {DesignTokens.ACCENT_PRIMARY};
            }}
        """
        temp_slider.setStyleSheet(slider_style)

        lbl_temp_val = QLabel("0.70")
        lbl_temp_val.setStyleSheet(f"color: {DesignTokens.ACCENT_PRIMARY}; font-size: 11px; font-weight: bold;")
        temp_slider.valueChanged.connect(lambda v, lbl=lbl_temp_val: lbl.setText(f"{v / 100:.2f}"))

        adv_layout.addWidget(lbl_temp)
        adv_layout.addWidget(temp_slider)
        adv_layout.addWidget(lbl_temp_val)

        lbl_tok = QLabel("Max Tokens :")
        lbl_tok.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold; margin-left: 12px;")

        tok_slider = QSlider(Qt.Orientation.Horizontal)
        tok_slider.setRange(256, 8192)
        tok_slider.setValue(4096)
        tok_slider.setFixedWidth(110)
        tok_slider.setStyleSheet(slider_style)

        lbl_tok_val = QLabel("4096")
        lbl_tok_val.setStyleSheet(f"color: {DesignTokens.ACCENT_PRIMARY}; font-size: 11px; font-weight: bold;")
        tok_slider.valueChanged.connect(lambda v, lbl=lbl_tok_val: lbl.setText(str(v)))

        adv_layout.addWidget(lbl_tok)
        adv_layout.addWidget(tok_slider)
        adv_layout.addWidget(lbl_tok_val)
        adv_layout.addStretch()

        return adv_widget, temp_slider, tok_slider

    def _setup_ui(self) -> None:
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(0)

        self.ab_panel = IdePanel(detachable=True)
        self.ab_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        ab_content = QWidget()
        ab_layout = QVBoxLayout(ab_content)
        ab_layout.setContentsMargins(12, 12, 12, 12)
        ab_layout.setSpacing(10)

        # ── 1. BARRE DE CONFIGURATION SUPÉRIEURE ───────────────────────────────
        self.config_bar_widget = QWidget()
        self.config_bar_widget.setObjectName("ConfigBarWidget")
        self._apply_config_bar_style()

        config_bar_layout = QVBoxLayout(self.config_bar_widget)
        config_bar_layout.setContentsMargins(12, 10, 12, 10)
        config_bar_layout.setSpacing(8)

        # Ligne 1 : Sélections (Mode, Contexte Commun, Modèle Cible)
        row1 = QHBoxLayout()
        row1.setContentsMargins(0, 0, 0, 0)
        row1.setSpacing(12)

        lbl_mode = QLabel("MODE :")
        lbl_mode.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold; letter-spacing: 0.5px;")
        row1.addWidget(lbl_mode, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.mode_combo = StyledComboBox()
        self.mode_combo.setMinimumWidth(220)
        self.mode_combo.setFixedHeight(30)
        self.mode_combo.addItem(load_phosphor_icon("ph.cpu", color=DesignTokens.ACCENT_PRIMARY), "Comparer deux Moteurs IA")
        self.mode_combo.addItem(load_phosphor_icon("ph.sparkle", color=DesignTokens.COLOR_YELLOW), "Comparer deux Prompts / Personas")
        self.mode_combo.addItem(load_phosphor_icon("ph.git-branch", color=DesignTokens.COLOR_GREEN), "Comparer deux Pipelines DAG")
        row1.addWidget(self.mode_combo, alignment=Qt.AlignmentFlag.AlignVCenter)

        # Agent Commun
        self.global_persona_widget = QWidget()
        gp_layout = QHBoxLayout(self.global_persona_widget)
        gp_layout.setContentsMargins(0, 0, 0, 0)
        gp_layout.setSpacing(6)
        lbl_gp = QLabel("Agent Commun :")
        lbl_gp.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
        self.persona_combo = StyledComboBox()
        self.persona_combo.setMinimumWidth(170)
        self.persona_combo.setFixedHeight(30)
        gp_layout.addWidget(lbl_gp)
        gp_layout.addWidget(self.persona_combo)
        row1.addWidget(self.global_persona_widget, alignment=Qt.AlignmentFlag.AlignVCenter)

        # Moteur Commun
        self.global_engine_widget = QWidget()
        ge_layout = QHBoxLayout(self.global_engine_widget)
        ge_layout.setContentsMargins(0, 0, 0, 0)
        ge_layout.setSpacing(6)
        lbl_ge = QLabel("Moteur Commun :")
        lbl_ge.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
        self.global_engine_combo = StyledComboBox()
        self.global_engine_combo.setMinimumWidth(170)
        self.global_engine_combo.setFixedHeight(30)
        ge_layout.addWidget(lbl_ge)
        ge_layout.addWidget(self.global_engine_combo)
        row1.addWidget(self.global_engine_widget, alignment=Qt.AlignmentFlag.AlignVCenter)
        self.global_engine_widget.hide()

        # Modèle NoteType cible
        lbl_nt = QLabel("Modèle Cible :")
        lbl_nt.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
        row1.addWidget(lbl_nt, alignment=Qt.AlignmentFlag.AlignVCenter)
        self.model_combo = StyledComboBox()
        self.model_combo.setMinimumWidth(160)
        self.model_combo.setFixedHeight(30)
        row1.addWidget(self.model_combo, alignment=Qt.AlignmentFlag.AlignVCenter)

        row1.addStretch()
        config_bar_layout.addLayout(row1)

        # Ligne 2 : Paquet Cible, Actions, Options et Lancement
        row2 = QHBoxLayout()
        row2.setContentsMargins(0, 0, 0, 0)
        row2.setSpacing(12)

        lbl_deck = QLabel("Paquet Cible :")
        lbl_deck.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
        row2.addWidget(lbl_deck, alignment=Qt.AlignmentFlag.AlignVCenter)
        self.deck_combo = StyledComboBox()
        self.deck_combo.setMinimumWidth(140)
        self.deck_combo.setFixedHeight(30)
        row2.addWidget(self.deck_combo, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.btn_adv_toggle = SecondaryButton("Réglages Inférence")
        self.btn_adv_toggle.setIcon(load_phosphor_icon("ph.sliders", color=DesignTokens.TEXT_PRIMARY))
        self.btn_adv_toggle.setFixedHeight(28)
        self.btn_adv_toggle.clicked.connect(self._toggle_advanced_drawer)
        row2.addWidget(self.btn_adv_toggle, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.chk_sync_nav = QCheckBox("Synchronisation Navigation A ↔ B")
        self.chk_sync_nav.setChecked(True)
        self.chk_sync_nav.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_sync_nav.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11.5px; font-weight: 500;")
        row2.addWidget(self.chk_sync_nav, alignment=Qt.AlignmentFlag.AlignVCenter)

        row2.addStretch()

        self.btn_run = PrimaryButton("Lancer le Test A/B")
        self.btn_run.setIcon(load_phosphor_icon("ph.play", color="white"))
        self.btn_run.setIconSize(QSize(15, 15))
        self.btn_run.setFixedHeight(32)
        self.btn_run.setMinimumWidth(200)
        apply_shadow(self.btn_run, blur=14, offset_y=0, color="rgba(99, 102, 241, 0.7)")
        row2.addWidget(self.btn_run, alignment=Qt.AlignmentFlag.AlignVCenter)

        config_bar_layout.addLayout(row2)
        ab_layout.addWidget(self.config_bar_widget)

        # ── 2. TIROIR PARAMÈTRES AVANCÉS (Inférence) ──────────────────────────
        self.adv_drawer = QFrame()
        self.adv_drawer.setObjectName("AdvDrawer")
        adv_drawer_layout = QVBoxLayout(self.adv_drawer)
        adv_drawer_layout.setContentsMargins(10, 6, 10, 6)
        adv_drawer_layout.setSpacing(6)

        self.global_adv_widget, self.global_temp_slider, self.global_tok_slider = self._build_advanced_settings()
        self.temp_slider_a = self.global_temp_slider
        self.tok_slider_a = self.global_tok_slider
        self.temp_slider_b = self.global_temp_slider
        self.tok_slider_b = self.global_tok_slider

        adv_drawer_layout.addWidget(self.global_adv_widget)
        self.adv_drawer.hide()
        ab_layout.addWidget(self.adv_drawer)

        # ── 3. TIROIR TEXTE SOURCE REPLIABLE ──────────────────────────────────
        self.source_box = QFrame()
        self.source_box.setObjectName("SourceBox")
        self._apply_source_box_style()

        source_layout = QVBoxLayout(self.source_box)
        source_layout.setContentsMargins(12, 8, 12, 8)
        source_layout.setSpacing(6)

        src_header = QHBoxLayout()
        src_header.setSpacing(8)

        lbl_src_icon = QLabel()
        lbl_src_icon.setFixedSize(16, 16)
        lbl_src_icon.setPixmap(load_phosphor_icon("ph.text-align-left", color=DesignTokens.TEXT_MUTED).pixmap(14, 14))
        src_header.addWidget(lbl_src_icon, alignment=Qt.AlignmentFlag.AlignVCenter)

        lbl_src_title = QLabel("TEXTE SOURCE D'ENTRÉE :")
        lbl_src_title.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        src_header.addWidget(lbl_src_title, alignment=Qt.AlignmentFlag.AlignVCenter)

        for label, text_content, var_style in PRESET_SAMPLES:
            btn_preset = TagPillButton(f"+ {label}", text_content, tooltip=f"Insère un exemple : {label}", variant=var_style)
            btn_preset.clicked.connect(lambda _, txt=text_content: self.source_text_edit.setPlainText(txt))
            src_header.addWidget(btn_preset, alignment=Qt.AlignmentFlag.AlignVCenter)

        src_header.addStretch()

        self.lbl_src_chars = QLabel("0 caractères")
        self.lbl_src_chars.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10.5px; font-family: monospace;")
        src_header.addWidget(self.lbl_src_chars, alignment=Qt.AlignmentFlag.AlignVCenter)

        btn_clear_src = IconButton("ph.trash", tooltip="Effacer le texte source", size=22)
        btn_clear_src.clicked.connect(lambda: self.source_text_edit.clear())
        src_header.addWidget(btn_clear_src, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.btn_toggle_source = IconButton("ph.caret-up", tooltip="Replier / Déplier le texte source", size=22)
        self.btn_toggle_source.clicked.connect(self._toggle_source_drawer)
        src_header.addWidget(self.btn_toggle_source, alignment=Qt.AlignmentFlag.AlignVCenter)

        source_layout.addLayout(src_header)

        self.source_text_edit.setPlaceholderText("Collez ici l'extrait de cours ou la consigne à tester dans le laboratoire A/B...")
        self.source_text_edit.setFixedHeight(75)
        self.source_text_edit.textChanged.connect(self._on_source_text_changed)
        source_layout.addWidget(self.source_text_edit)

        ab_layout.addWidget(self.source_box)

        # ── 4. BARRE CENTRALE DE COMMUTATION DE REPRÉSENTATION ─────────────────
        switcher_bar = QHBoxLayout()
        switcher_bar.setSpacing(6)

        lbl_view_mode = QLabel("VUE COMPARATIVE :")
        lbl_view_mode.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        switcher_bar.addWidget(lbl_view_mode, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.btn_subtab_preview = SubTabButton("Rendu Visuel", "ph.eye", is_active=True)
        self.btn_subtab_preview.clicked.connect(lambda: self._switch_view_mode(0))
        switcher_bar.addWidget(self.btn_subtab_preview, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.btn_subtab_table = SubTabButton("Tableau des Champs", "ph.table", is_active=False)
        self.btn_subtab_table.clicked.connect(lambda: self._switch_view_mode(1))
        switcher_bar.addWidget(self.btn_subtab_table, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.btn_subtab_json = SubTabButton("JSON Brut", "ph.code", is_active=False)
        self.btn_subtab_json.clicked.connect(lambda: self._switch_view_mode(2))
        switcher_bar.addWidget(self.btn_subtab_json, alignment=Qt.AlignmentFlag.AlignVCenter)

        switcher_bar.addStretch()

        self.btn_flip_both = SecondaryButton("Retourner (Verso)")
        self.btn_flip_both.setIcon(load_phosphor_icon("ph.arrow-clockwise", color=DesignTokens.TEXT_PRIMARY))
        self.btn_flip_both.setFixedHeight(28)
        self.btn_flip_both.clicked.connect(self._on_flip_both_cards)
        switcher_bar.addWidget(self.btn_flip_both, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.btn_device_desktop = IconButton("ph.monitor", tooltip="Mode Bureau (100% largeur)", size=24)
        self.btn_device_desktop.clicked.connect(lambda: self._set_both_device_mode("desktop"))
        switcher_bar.addWidget(self.btn_device_desktop, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.btn_device_tablet = IconButton("ph.device-tablet", tooltip="Mode Tablette (768px)", size=24)
        self.btn_device_tablet.clicked.connect(lambda: self._set_both_device_mode("tablet"))
        switcher_bar.addWidget(self.btn_device_tablet, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.btn_device_mobile = IconButton("ph.device-mobile", tooltip="Mode Mobile (375px)", size=24)
        self.btn_device_mobile.clicked.connect(lambda: self._set_both_device_mode("mobile"))
        switcher_bar.addWidget(self.btn_device_mobile, alignment=Qt.AlignmentFlag.AlignVCenter)

        ab_layout.addLayout(switcher_bar)

        # ── 5. COMPARATIF CÔTE-À-CÔTE (BRANCHE A VS BRANCHE B) ─────────────────
        self.compare_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.compare_splitter.setStyleSheet(f"""
            QSplitter::handle {{
                background-color: {DesignTokens.BORDER_COLOR};
                width: 3px;
                border-radius: 1px;
            }}
            QSplitter::handle:hover {{
                background-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        ab_layout.addWidget(self.compare_splitter, 1)

        # ── PANNEAU A ──
        self.panel_a = QFrame()
        self.panel_a.setObjectName("PanelA")
        layout_a = QVBoxLayout(self.panel_a)
        layout_a.setContentsMargins(10, 10, 10, 10)
        layout_a.setSpacing(8)

        toolbar_a = QHBoxLayout()
        toolbar_a.setContentsMargins(0, 0, 0, 0)
        toolbar_a.setSpacing(8)

        self.lbl_a = QLabel("Moteur A :")
        self.lbl_a.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
        self.engine_a_combo = StyledComboBox()
        self.engine_a_combo.setFixedHeight(30)
        self.persona_a_combo = StyledComboBox()
        self.persona_a_combo.setFixedHeight(30)
        self.persona_a_combo.hide()
        self.pipeline_a_combo = StyledComboBox()
        self.pipeline_a_combo.setFixedHeight(30)
        self.pipeline_a_combo.hide()

        self.btn_import_a = SecondaryButton("Importer dans la Forge")
        self.btn_import_a.setIcon(load_phosphor_icon("ph.arrow-down", color=DesignTokens.TEXT_PRIMARY))
        self.btn_import_a.setFixedHeight(28)
        self.btn_import_a.clicked.connect(lambda: self._on_import_branch_to_forge("A"))

        toolbar_a.addWidget(self.lbl_a, alignment=Qt.AlignmentFlag.AlignVCenter)
        toolbar_a.addWidget(self.engine_a_combo, 1, alignment=Qt.AlignmentFlag.AlignVCenter)
        toolbar_a.addWidget(self.persona_a_combo, 1, alignment=Qt.AlignmentFlag.AlignVCenter)
        toolbar_a.addWidget(self.pipeline_a_combo, 1, alignment=Qt.AlignmentFlag.AlignVCenter)
        toolbar_a.addWidget(self.btn_import_a, alignment=Qt.AlignmentFlag.AlignVCenter)
        layout_a.addLayout(toolbar_a)

        self.kpi_a = BranchKpiWidget("BRANCHE A", color_hex="#8b5cf6")
        layout_a.addWidget(self.kpi_a)

        self.stack_a = QStackedWidget()
        self.preview_a = CardPreviewWidget(show_header=False)
        if hasattr(self.preview_a, "controls_container"):
            self.preview_a.controls_container.hide()

        self.table_a = QTableWidget()
        self.table_a.setColumnCount(2)
        self.table_a.setHorizontalHeaderLabels(["Champ NoteType", "Valeur Générée"])
        self.table_a.horizontalHeader().setStretchLastSection(True)
        self.table_a.verticalHeader().setVisible(False)
        self.table_a.setColumnWidth(0, 140)

        self.json_edit_a = StyledTextEdit()
        self.json_edit_a.setReadOnly(True)

        self.stack_a.addWidget(self.preview_a)
        self.stack_a.addWidget(self.table_a)
        self.stack_a.addWidget(self.json_edit_a)
        layout_a.addWidget(self.stack_a, 1)

        self.compare_splitter.addWidget(self.panel_a)

        # ── PANNEAU B ──
        self.panel_b = QFrame()
        self.panel_b.setObjectName("PanelB")
        layout_b = QVBoxLayout(self.panel_b)
        layout_b.setContentsMargins(10, 10, 10, 10)
        layout_b.setSpacing(8)

        toolbar_b = QHBoxLayout()
        toolbar_b.setContentsMargins(0, 0, 0, 0)
        toolbar_b.setSpacing(8)

        self.lbl_b = QLabel("Moteur B :")
        self.lbl_b.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
        self.engine_b_combo = StyledComboBox()
        self.engine_b_combo.setFixedHeight(30)
        self.persona_b_combo = StyledComboBox()
        self.persona_b_combo.setFixedHeight(30)
        self.persona_b_combo.hide()
        self.pipeline_b_combo = StyledComboBox()
        self.pipeline_b_combo.setFixedHeight(30)
        self.pipeline_b_combo.hide()

        self.btn_import_b = SecondaryButton("Importer dans la Forge")
        self.btn_import_b.setIcon(load_phosphor_icon("ph.arrow-down", color=DesignTokens.TEXT_PRIMARY))
        self.btn_import_b.setFixedHeight(28)
        self.btn_import_b.clicked.connect(lambda: self._on_import_branch_to_forge("B"))

        toolbar_b.addWidget(self.lbl_b, alignment=Qt.AlignmentFlag.AlignVCenter)
        toolbar_b.addWidget(self.engine_b_combo, 1, alignment=Qt.AlignmentFlag.AlignVCenter)
        toolbar_b.addWidget(self.persona_b_combo, 1, alignment=Qt.AlignmentFlag.AlignVCenter)
        toolbar_b.addWidget(self.pipeline_b_combo, 1, alignment=Qt.AlignmentFlag.AlignVCenter)
        toolbar_b.addWidget(self.btn_import_b, alignment=Qt.AlignmentFlag.AlignVCenter)
        layout_b.addLayout(toolbar_b)

        self.kpi_b = BranchKpiWidget("BRANCHE B", color_hex="#06b6d4")
        layout_b.addWidget(self.kpi_b)

        self.stack_b = QStackedWidget()
        self.preview_b = CardPreviewWidget(show_header=False)
        if hasattr(self.preview_b, "controls_container"):
            self.preview_b.controls_container.hide()

        self.table_b = QTableWidget()
        self.table_b.setColumnCount(2)
        self.table_b.setHorizontalHeaderLabels(["Champ NoteType", "Valeur Générée"])
        self.table_b.horizontalHeader().setStretchLastSection(True)
        self.table_b.verticalHeader().setVisible(False)
        self.table_b.setColumnWidth(0, 140)

        self.json_edit_b = StyledTextEdit()
        self.json_edit_b.setReadOnly(True)

        self.stack_b.addWidget(self.preview_b)
        self.stack_b.addWidget(self.table_b)
        self.stack_b.addWidget(self.json_edit_b)
        layout_b.addWidget(self.stack_b, 1)

        self.compare_splitter.addWidget(self.panel_b)
        self.compare_splitter.setSizes([500, 500])

        # ── 6. BARRE DE PAGINATION INTÉGRÉE ──────────────────────────────────
        pagination_bar = QHBoxLayout()
        pagination_bar.setContentsMargins(10, 4, 10, 4)
        pagination_bar.setSpacing(12)

        nav_a_box = QHBoxLayout()
        nav_a_box.setSpacing(6)
        lbl_pag_a = QLabel("Branche A :")
        lbl_pag_a.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
        self.btn_prev_a = IconButton("ph.caret-left", size=22)
        self.lbl_count_a = QLabel("0 / 0")
        self.lbl_count_a.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-family: '{DesignTokens.FONT_CODE}'; font-size: 11px; font-weight: bold;")
        self.btn_next_a = IconButton("ph.caret-right", size=22)
        nav_a_box.addWidget(lbl_pag_a)
        nav_a_box.addWidget(self.btn_prev_a)
        nav_a_box.addWidget(self.lbl_count_a)
        nav_a_box.addWidget(self.btn_next_a)
        pagination_bar.addLayout(nav_a_box)

        pagination_bar.addStretch()

        lbl_shortcut = QLabel("Raccourci : Ctrl+Entrée pour lancer")
        lbl_shortcut.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10.5px; font-style: italic;")
        pagination_bar.addWidget(lbl_shortcut)

        pagination_bar.addStretch()

        nav_b_box = QHBoxLayout()
        nav_b_box.setSpacing(6)
        lbl_pag_b = QLabel("Branche B :")
        lbl_pag_b.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
        self.btn_prev_b = IconButton("ph.caret-left", size=22)
        self.lbl_count_b = QLabel("0 / 0")
        self.lbl_count_b.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-family: '{DesignTokens.FONT_CODE}'; font-size: 11px; font-weight: bold;")
        self.btn_next_b = IconButton("ph.caret-right", size=22)
        nav_b_box.addWidget(lbl_pag_b)
        nav_b_box.addWidget(self.btn_prev_b)
        nav_b_box.addWidget(self.lbl_count_b)
        nav_b_box.addWidget(self.btn_next_b)
        pagination_bar.addLayout(nav_b_box)

        ab_layout.addLayout(pagination_bar)

        self._apply_theme_to_widgets()

        self.ab_panel.add_tab("Laboratoire A/B", ab_content, "ph.scales", closable=False)
        main_layout.addWidget(self.ab_panel, 1)

        shortcut_run = QShortcut(QKeySequence("Ctrl+Return"), self)
        shortcut_run.activated.connect(self._on_run_ab_test)

    def _apply_config_bar_style(self) -> None:
        self.config_bar_widget.setStyleSheet(f"""
            QWidget#ConfigBarWidget {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
            QWidget#ConfigBarWidget QLabel {{
                background: transparent;
            }}
        """)

    def _apply_source_box_style(self) -> None:
        self.source_box.setStyleSheet(f"""
            QFrame#SourceBox {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
            QFrame#SourceBox QLabel {{
                background: transparent;
            }}
        """)

    def _apply_theme_to_widgets(self) -> None:
        self._apply_config_bar_style()
        self._apply_source_box_style()

        panel_css = f"""
            QFrame#PanelA, QFrame#PanelB {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
            QFrame#PanelA QLabel, QFrame#PanelB QLabel {{
                background: transparent;
            }}
        """
        self.panel_a.setStyleSheet(panel_css)
        self.panel_b.setStyleSheet(panel_css)

        self.adv_drawer.setStyleSheet(f"""
            QFrame#AdvDrawer {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)

        self.source_text_edit.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {DesignTokens.BG_INPUT};
                color: {DesignTokens.TEXT_PRIMARY};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 6px;
                font-size: 12px;
            }}
        """)

        table_css = f"""
            QTableWidget {{
                background-color: {DesignTokens.BG_INPUT};
                color: {DesignTokens.TEXT_PRIMARY};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                gridline-color: {DesignTokens.BORDER_COLOR};
                selection-background-color: {DesignTokens.BG_HOVER};
                selection-color: {DesignTokens.TEXT_PRIMARY};
            }}
            QHeaderView::section {{
                background-color: {DesignTokens.BG_PANEL};
                color: {DesignTokens.TEXT_MUTED};
                font-weight: bold;
                font-size: 11px;
                border: none;
                border-right: 1px solid {DesignTokens.BORDER_COLOR};
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
                padding: 6px 12px;
            }}
        """
        self.table_a.setStyleSheet(table_css)
        self.table_b.setStyleSheet(table_css)

        json_css = f"""
            QPlainTextEdit {{
                background-color: {DesignTokens.BG_INPUT};
                color: {DesignTokens.COLOR_BLUE};
                font-family: '{DesignTokens.FONT_CODE}', monospace;
                font-size: 11.5px;
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 8px;
            }}
        """
        self.json_edit_a.setStyleSheet(json_css)
        self.json_edit_b.setStyleSheet(json_css)

        if hasattr(self, "kpi_a"):
            self.kpi_a._apply_style()
        if hasattr(self, "kpi_b"):
            self.kpi_b._apply_style()

    def _connect_signals(self) -> None:
        self.btn_run.clicked.connect(self._on_run_ab_test)

        self.btn_prev_a.clicked.connect(self._prev_a)
        self.btn_next_a.clicked.connect(self._next_a)

        self.btn_prev_b.clicked.connect(self._prev_b)
        self.btn_next_b.clicked.connect(self._next_b)

        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)

    def _on_source_text_changed(self) -> None:
        cnt = len(self.source_text_edit.toPlainText())
        self.lbl_src_chars.setText(f"{cnt} caractère{'s' if cnt > 1 else ''}")

    def _toggle_source_drawer(self) -> None:
        self._source_collapsed = not self._source_collapsed
        self.source_text_edit.setVisible(not self._source_collapsed)
        if self._source_collapsed:
            self.btn_toggle_source.setIcon(load_phosphor_icon("ph.caret-down", color=DesignTokens.TEXT_MUTED))
            self.btn_toggle_source.setToolTip("Déplier le texte source")
        else:
            self.btn_toggle_source.setIcon(load_phosphor_icon("ph.caret-up", color=DesignTokens.TEXT_MUTED))
            self.btn_toggle_source.setToolTip("Replier le texte source")

    def _toggle_advanced_drawer(self) -> None:
        self._adv_collapsed = not self._adv_collapsed
        self.adv_drawer.setVisible(not self._adv_collapsed)

    def _switch_view_mode(self, mode_idx: int) -> None:
        self.btn_subtab_preview.set_active(mode_idx == 0)
        self.btn_subtab_table.set_active(mode_idx == 1)
        self.btn_subtab_json.set_active(mode_idx == 2)
        self.stack_a.setCurrentIndex(mode_idx)
        self.stack_b.setCurrentIndex(mode_idx)

    def _on_flip_both_cards(self) -> None:
        if hasattr(self.preview_a, "flip_card"):
            self.preview_a.flip_card()
        if hasattr(self.preview_b, "flip_card"):
            self.preview_b.flip_card()

    def _set_both_device_mode(self, mode: str) -> None:
        if hasattr(self.preview_a, "set_device_mode"):
            self.preview_a.set_device_mode(mode)
        if hasattr(self.preview_b, "set_device_mode"):
            self.preview_b.set_device_mode(mode)

    @Slot()
    def _on_mode_changed(self) -> None:
        idx = self.mode_combo.currentIndex()
        if idx == 0:
            self.global_persona_widget.show()
            self.global_engine_widget.hide()

            self.lbl_a.setText("Moteur A :")
            self.engine_a_combo.show()
            self.persona_a_combo.hide()
            self.pipeline_a_combo.hide()

            self.lbl_b.setText("Moteur B :")
            self.engine_b_combo.show()
            self.persona_b_combo.hide()
            self.pipeline_b_combo.hide()
        elif idx == 1:
            self.global_persona_widget.hide()
            self.global_engine_widget.show()

            self.lbl_a.setText("Prompt A :")
            self.engine_a_combo.hide()
            self.persona_a_combo.show()
            self.pipeline_a_combo.hide()

            self.lbl_b.setText("Prompt B :")
            self.engine_b_combo.hide()
            self.persona_b_combo.show()
            self.pipeline_b_combo.hide()
        else:
            self.global_persona_widget.hide()
            self.global_engine_widget.show()

            self.lbl_a.setText("Pipeline A :")
            self.engine_a_combo.hide()
            self.persona_a_combo.hide()
            self.pipeline_a_combo.show()

            self.lbl_b.setText("Pipeline B :")
            self.engine_b_combo.hide()
            self.persona_b_combo.hide()
            self.pipeline_b_combo.show()

    def refresh_data(self) -> None:
        try:
            self.engine_a_combo.blockSignals(True)
            self.engine_b_combo.blockSignals(True)
            self.global_engine_combo.blockSignals(True)
            self.engine_a_combo.clear()
            self.engine_b_combo.clear()
            self.global_engine_combo.clear()

            engines = list(LLMConfigModel.select())
            for eg in engines:
                name = eg.display_name or eg.provider
                self.engine_a_combo.addItem(name, userData=eg)
                self.engine_b_combo.addItem(name, userData=eg)
                self.global_engine_combo.addItem(name, userData=eg)
            if len(engines) > 1:
                self.engine_b_combo.setCurrentIndex(1)

            self.engine_a_combo.blockSignals(False)
            self.engine_b_combo.blockSignals(False)
            self.global_engine_combo.blockSignals(False)

            self.persona_combo.blockSignals(True)
            self.persona_a_combo.blockSignals(True)
            self.persona_b_combo.blockSignals(True)
            self.persona_combo.clear()
            self.persona_a_combo.clear()
            self.persona_b_combo.clear()
            personas = list(PersonaModel.select())
            for ag in personas:
                self.persona_combo.addItem(ag.name, userData=ag)
                self.persona_a_combo.addItem(ag.name, userData=ag)
                self.persona_b_combo.addItem(ag.name, userData=ag)
            if len(personas) > 1:
                self.persona_b_combo.setCurrentIndex(1)
            self.persona_combo.blockSignals(False)
            self.persona_a_combo.blockSignals(False)
            self.persona_b_combo.blockSignals(False)

            self.pipeline_a_combo.blockSignals(True)
            self.pipeline_b_combo.blockSignals(True)
            self.pipeline_a_combo.clear()
            self.pipeline_b_combo.clear()
            pipelines = list(PipelineModel.select())
            for pipe in pipelines:
                self.pipeline_a_combo.addItem(pipe.name, userData=pipe)
                self.pipeline_b_combo.addItem(pipe.name, userData=pipe)
            if len(pipelines) > 1:
                self.pipeline_b_combo.setCurrentIndex(1)
            self.pipeline_a_combo.blockSignals(False)
            self.pipeline_b_combo.blockSignals(False)

            self.model_combo.blockSignals(True)
            self.model_combo.clear()
            for nt in NoteTypeModel.select():
                self.model_combo.addItem(nt.name, userData=nt)
            self.model_combo.blockSignals(False)

            self.deck_combo.blockSignals(True)
            self.deck_combo.clear()
            decks = list(DeckModel.select())
            if not decks:
                default_d = DeckModel.create(name="Défaut")
                decks = [default_d]
            for d in decks:
                self.deck_combo.addItem(d.name, userData=d)
            self.deck_combo.blockSignals(False)

        except Exception as e:
            logger.warning("Erreur refresh_data ab_tests_view: %s", e)

    def is_dirty(self) -> bool:
        return False

    def _insert_mock_initial_data(self) -> None:
        self.source_text_edit.setPlainText(PRESET_SAMPLES[0][1])

        self.cards_a = [
            {
                "Front": "Quelle est la caractéristique principale de l'insuffisance cardiaque droite ?",
                "Back": "Incapacité du VD à assurer un débit sanguin pulmonaire suffisant.",
            }
        ]
        self.cards_b = [
            {
                "Front": "L'insuffisance cardiaque droite concerne le ventricule {{c1::droit}}.",
                "Back": "Signes cliniques : Turgescence jugulaire et reflux hépato-jugulaire.",
            }
        ]
        self._update_views()

    def _update_views(self) -> None:
        selected_nt = self.model_combo.currentData()
        fields = ["Front", "Back"]
        if selected_nt and getattr(selected_nt, "fields_schema", None):
            try:
                fields = json.loads(selected_nt.fields_schema)
            except Exception:
                pass  # nosec B110

        f_front = fields[0] if len(fields) > 0 else "Front"
        f_back = fields[1] if len(fields) > 1 else "Back"

        # Side A
        if self.cards_a:
            self.lbl_count_a.setText(f"{self.index_a + 1} / {len(self.cards_a)}")
            current_card_a = self.cards_a[self.index_a]
            self.json_edit_a.setPlainText(json.dumps(current_card_a, ensure_ascii=False, indent=2))

            self.table_a.setRowCount(len(current_card_a))
            for row, (k, v) in enumerate(current_card_a.items()):
                self.table_a.setItem(row, 0, QTableWidgetItem(str(k)))
                self.table_a.setItem(row, 1, QTableWidgetItem(str(v)))

            qfmt_a = current_card_a.get(f_front) or current_card_a.get(f_front.lower()) or f"{{{{{f_front}}}}}"
            back_val_a = current_card_a.get(f_back) or current_card_a.get(f_back.lower()) or f"{{{{{f_back}}}}}"
            afmt_a = f'{{{{FrontSide}}}}<br><hr id="answer"><br>{back_val_a}'
            tmpl_a = {"name": "Carte 1", "qfmt": qfmt_a, "afmt": afmt_a}

            self.preview_a.update_preview(
                note_type=selected_nt,
                fields_dict=current_card_a,
                override_templates=[tmpl_a],
            )
        else:
            self.lbl_count_a.setText("0 / 0")
            self.table_a.setRowCount(0)
            self.json_edit_a.clear()

        # Side B
        if self.cards_b:
            self.lbl_count_b.setText(f"{self.index_b + 1} / {len(self.cards_b)}")
            current_card_b = self.cards_b[self.index_b]
            self.json_edit_b.setPlainText(json.dumps(current_card_b, ensure_ascii=False, indent=2))

            self.table_b.setRowCount(len(current_card_b))
            for row, (k, v) in enumerate(current_card_b.items()):
                self.table_b.setItem(row, 0, QTableWidgetItem(str(k)))
                self.table_b.setItem(row, 1, QTableWidgetItem(str(v)))

            qfmt_b = current_card_b.get(f_front) or current_card_b.get(f_front.lower()) or f"{{{{{f_front}}}}}"
            back_val_b = current_card_b.get(f_back) or current_card_b.get(f_back.lower()) or f"{{{{{f_back}}}}}"
            afmt_b = f'{{{{FrontSide}}}}<br><hr id="answer"><br>{back_val_b}'
            tmpl_b = {"name": "Carte 1", "qfmt": qfmt_b, "afmt": afmt_b}

            self.preview_b.update_preview(
                note_type=selected_nt,
                fields_dict=current_card_b,
                override_templates=[tmpl_b],
            )
        else:
            self.lbl_count_b.setText("0 / 0")
            self.table_b.setRowCount(0)
            self.json_edit_b.clear()

    @Slot()
    def _prev_a(self) -> None:
        if self.cards_a and self.index_a > 0:
            self.index_a -= 1
            if self.chk_sync_nav.isChecked() and self.cards_b and self.index_b > 0:
                self.index_b -= 1
            self._update_views()

    @Slot()
    def _next_a(self) -> None:
        if self.cards_a and self.index_a < len(self.cards_a) - 1:
            self.index_a += 1
            if self.chk_sync_nav.isChecked() and self.cards_b and self.index_b < len(self.cards_b) - 1:
                self.index_b += 1
            self._update_views()

    @Slot()
    def _prev_b(self) -> None:
        if self.cards_b and self.index_b > 0:
            self.index_b -= 1
            if self.chk_sync_nav.isChecked() and self.cards_a and self.index_a > 0:
                self.index_a -= 1
            self._update_views()

    @Slot()
    def _next_b(self) -> None:
        if self.cards_b and self.index_b < len(self.cards_b) - 1:
            self.index_b += 1
            if self.chk_sync_nav.isChecked() and self.cards_a and self.index_a < len(self.cards_a) - 1:
                self.index_a += 1
            self._update_views()

    @Slot()
    def _on_run_ab_test(self) -> None:
        text_source = self.source_text_edit.toPlainText().strip()
        if not text_source:
            show_toast(self, "Veuillez saisir un texte source à tester.", is_error=True)
            return

        selected_nt = self.model_combo.currentData()
        nt_id = selected_nt.id if selected_nt and hasattr(selected_nt, "id") else 1
        nt_schema = json.loads(selected_nt.fields_schema) if selected_nt and selected_nt.fields_schema else ["Front", "Back"]

        mode_idx = self.mode_combo.currentIndex()

        steps_a = None
        steps_b = None

        if mode_idx == 0:
            engine_a = self.engine_a_combo.currentData()
            engine_b = self.engine_b_combo.currentData()
            pipe_id_a = None
            pipe_id_b = None
            common_persona = self.persona_combo.currentData()
            if common_persona:
                steps_a = [PipelineStepModel(persona=common_persona, step_type="LLM_PROMPT", step_order=1)]
                steps_b = [PipelineStepModel(persona=common_persona, step_type="LLM_PROMPT", step_order=1)]

        elif mode_idx == 1:
            engine_a = self.global_engine_combo.currentData()
            engine_b = self.global_engine_combo.currentData()
            pipe_id_a = None
            pipe_id_b = None
            p_a = self.persona_a_combo.currentData()
            p_b = self.persona_b_combo.currentData()
            if p_a:
                steps_a = [PipelineStepModel(persona=p_a, step_type="LLM_PROMPT", step_order=1)]
            if p_b:
                steps_b = [PipelineStepModel(persona=p_b, step_type="LLM_PROMPT", step_order=1)]

        else:
            engine_a = self.global_engine_combo.currentData()
            engine_b = self.global_engine_combo.currentData()
            pipe_a = self.pipeline_a_combo.currentData()
            pipe_b = self.pipeline_b_combo.currentData()
            pipe_id_a = pipe_a.id if pipe_a else None
            pipe_id_b = pipe_b.id if pipe_b else None

        show_toast(self, "Lancement du test A/B en parallèle via le Moteur DAG...")
        self.btn_run.setEnabled(False)
        self._completed_a = False
        self._completed_b = False
        self.kpi_a.set_running()
        self.kpi_b.set_running()

        provider_a = None
        provider_b = None
        if self.ai_manager and hasattr(self.ai_manager, "create_provider_from_config"):
            try:
                if engine_a:
                    provider_a = self.ai_manager.create_provider_from_config(engine_a)
                if engine_b:
                    provider_b = self.ai_manager.create_provider_from_config(engine_b)
            except Exception as e:
                logger.warning("Erreur instanciation providers A/B: %s", e)

        state_a = PipelineRunState(initial_prompt=text_source[:120])
        state_a.set_variable("text_source", text_source)
        state_a.set_variable("fields", nt_schema)
        state_a.set_variable("note_type_id", nt_id)

        state_b = PipelineRunState(initial_prompt=text_source[:120])
        state_b.set_variable("text_source", text_source)
        state_b.set_variable("fields", nt_schema)
        state_b.set_variable("note_type_id", nt_id)

        self._start_time_a = time.perf_counter()
        self._start_time_b = time.perf_counter()

        self.orchestrator_a = PipelineOrchestrator(
            pipeline_id=pipe_id_a,
            initial_state=state_a,
            steps=steps_a,
            ai_provider=provider_a,
        )
        self.orchestrator_a.signals.pipeline_finished.connect(self._on_finished_a)
        self.orchestrator_a.signals.error_occurred.connect(lambda err: self._on_error_a(err))

        self.orchestrator_b = PipelineOrchestrator(
            pipeline_id=pipe_id_b,
            initial_state=state_b,
            steps=steps_b,
            ai_provider=provider_b,
        )
        self.orchestrator_b.signals.pipeline_finished.connect(self._on_finished_b)
        self.orchestrator_b.signals.error_occurred.connect(lambda err: self._on_error_b(err))

        QThreadPool.globalInstance().start(self.orchestrator_a)
        QThreadPool.globalInstance().start(self.orchestrator_b)

    def _extract_cards_from_state(self, state: PipelineRunState) -> list[dict[str, Any]]:
        raw_cards = state.get_variable("generated_cards") or state.get_variable("map_reduce_results") or state.get_variable("last_output") or []
        return extract_cards_from_data(raw_cards)

    @Slot(object)
    def _on_finished_a(self, state: PipelineRunState) -> None:
        elapsed = time.perf_counter() - self._start_time_a
        self.cards_a = self._extract_cards_from_state(state)
        self.index_a = 0
        self._completed_a = True

        tokens_est = len(str(self.cards_a)) // 4
        cost_est = (tokens_est / 1000) * 0.002
        self.kpi_a.set_results(elapsed=elapsed, cards_count=len(self.cards_a), tokens=tokens_est, cost_usd=cost_est, is_success=True)

        self._check_test_complete()

    @Slot(object)
    def _on_finished_b(self, state: PipelineRunState) -> None:
        elapsed = time.perf_counter() - self._start_time_b
        self.cards_b = self._extract_cards_from_state(state)
        self.index_b = 0
        self._completed_b = True

        tokens_est = len(str(self.cards_b)) // 4
        cost_est = (tokens_est / 1000) * 0.002
        self.kpi_b.set_results(elapsed=elapsed, cards_count=len(self.cards_b), tokens=tokens_est, cost_usd=cost_est, is_success=True)

        self._check_test_complete()

    def _on_error_a(self, err: str) -> None:
        elapsed = time.perf_counter() - self._start_time_a
        self._completed_a = True
        self.kpi_a.set_results(elapsed=elapsed, cards_count=0, tokens=0, cost_usd=0.0, is_success=False, err_msg=err)
        show_toast(self, f"Erreur Branche A: {err}", is_error=True)
        self._check_test_complete()

    def _on_error_b(self, err: str) -> None:
        elapsed = time.perf_counter() - self._start_time_b
        self._completed_b = True
        self.kpi_b.set_results(elapsed=elapsed, cards_count=0, tokens=0, cost_usd=0.0, is_success=False, err_msg=err)
        show_toast(self, f"Erreur Branche B: {err}", is_error=True)
        self._check_test_complete()

    def _evaluate_winner(self) -> None:
        time_a = self.kpi_a._last_elapsed
        time_b = self.kpi_b._last_elapsed
        cost_a = self.kpi_a._last_cost
        cost_b = self.kpi_b._last_cost

        if time_a > 0 and time_b > 0:
            if time_a < time_b * 0.90:
                ratio = time_b / time_a if time_a > 0 else 1.0
                self.kpi_a.set_winner(f"⚡ {ratio:.1f}x plus rapide")
                self.kpi_b.clear_winner()
            elif time_b < time_a * 0.90:
                ratio = time_a / time_b if time_b > 0 else 1.0
                self.kpi_b.set_winner(f"⚡ {ratio:.1f}x plus rapide")
                self.kpi_a.clear_winner()
            elif cost_a < cost_b * 0.85:
                self.kpi_a.set_winner("💰 Plus économique")
                self.kpi_b.clear_winner()
            elif cost_b < cost_a * 0.85:
                self.kpi_b.set_winner("💰 Plus économique")
                self.kpi_a.clear_winner()
            else:
                self.kpi_a.clear_winner()
                self.kpi_b.clear_winner()

    def _check_test_complete(self) -> None:
        if self._completed_a and self._completed_b:
            self.btn_run.setEnabled(True)
            self._evaluate_winner()
            self._update_views()
            show_toast(self, "Test A/B terminé avec succès !")

    def _on_import_branch_to_forge(self, branch: str) -> None:
        cards = self.cards_a if branch == "A" else self.cards_b
        if not cards:
            show_toast(self, f"Aucune carte à importer depuis la Branche {branch}.", is_error=True)
            return

        selected_nt = self.model_combo.currentData()
        if not selected_nt:
            selected_nt = NoteTypeModel.select().first()

        selected_deck = self.deck_combo.currentData()
        if not selected_deck:
            selected_deck = DeckModel.get_or_none(DeckModel.name == "Défaut")
            if not selected_deck:
                selected_deck = DeckModel.create(name="Défaut")

        try:
            imported_count = 0
            with db.atomic():
                for card_dict in cards:
                    note = NoteModel.create(
                        guid=uuid.uuid4().hex,
                        note_type=selected_nt,
                        tags="ab_test",
                    )
                    note.add_version(card_dict, source="ai_ab_test")
                    CardModel.create(note=note, deck=selected_deck, template_index=0)
                    imported_count += 1

            btn = self.btn_import_a if branch == "A" else self.btn_import_b
            btn.setText(f"✓ {imported_count} Importées")
            btn.setIcon(load_phosphor_icon("ph.check", color=DesignTokens.COLOR_GREEN))

            show_toast(self, f"{imported_count} cartes de la Branche {branch} importées dans le paquet '{selected_deck.name}' !")
        except Exception as e:
            logger.exception("Erreur lors de l'import des cartes A/B dans la Forge")
            show_toast(self, f"Erreur lors de l'import : {e}", is_error=True)

    def refresh_theme(self, profile: Any) -> None:
        self._apply_theme_to_widgets()
        if hasattr(self, "preview_a") and hasattr(self.preview_a, "refresh_theme"):
            self.preview_a.refresh_theme(profile)
        if hasattr(self, "preview_b") and hasattr(self.preview_b, "refresh_theme"):
            self.preview_b.refresh_theme(profile)

    def closeEvent(self, event: Any) -> None:
        if hasattr(self, "orchestrator_a") and self.orchestrator_a is not None:
            try:
                self.orchestrator_a.cancel()
            except Exception:
                pass  # nosec B110
        if hasattr(self, "orchestrator_b") and self.orchestrator_b is not None:
            try:
                self.orchestrator_b.cancel()
            except Exception:
                pass  # nosec B110
        if hasattr(self, "preview_a") and self.preview_a is not None:
            try:
                self.preview_a.close()
            except Exception:
                pass  # nosec B110
        if hasattr(self, "preview_b") and self.preview_b is not None:
            try:
                self.preview_b.close()
            except Exception:
                pass  # nosec B110
        super().closeEvent(event)


ABTestsTab = ABTestsView

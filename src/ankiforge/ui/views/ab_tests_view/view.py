import json
import logging
import os
import time
import uuid
from typing import Any

from PySide6.QtCore import QSize, Qt, QThreadPool, QTimer, Slot
from PySide6.QtGui import QFontMetrics, QKeySequence, QShortcut
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
    DeckModel,
    DocumentModel,
    NoteTypeModel,
    PersonaModel,
    PipelineModel,
    PipelineStepModel,
)
from ankiforge.services.ai.orchestrator import PipelineOrchestrator
from ankiforge.services.ai.pricing_service import estimate_run_cost
from ankiforge.services.ai.state import PipelineRunState
from ankiforge.services.ai.utils import extract_cards_from_data
from ankiforge.services.settings_service import SettingsService
from ankiforge.ui.components import (
    DocumentPickerButton,
    FlowLayout,
    IconButton,
    IdePanel,
    ModelSelectorWidget,
    PrimaryButton,
    SecondaryButton,
    StyledComboBox,
    StyledTextEdit,
)
from ankiforge.ui.theme import DesignTokens, apply_shadow
from ankiforge.ui.views.ab_tests_view.widgets import (
    BranchKpiWidget,
    SubTabButton,
)
from ankiforge.ui.views.creation_view.widgets.document_editor import DocumentEditorWidget
from ankiforge.ui.widgets.card_preview_widget import CardPreviewWidget
from ankiforge.ui.widgets.time_machine_dialog import DiffViewerWidget
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.icon_loader import load_on_accent_icon, load_phosphor_icon

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
        self._ab_run_id: str = ""

        self.summary_labels: dict[str, QLabel] = {}

        self.source_editor = DocumentEditorWidget(content="", source_title="Source Laboratoire A/B", doc_model=None)
        self.source_text_edit: StyledTextEdit = self.source_editor.raw_editor

        self._engine_cfg_a: Any = None
        self._engine_cfg_b: Any = None
        self._persona_cfg_a: Any = None
        self._persona_cfg_b: Any = None
        self._pipeline_cfg_a: Any = None
        self._pipeline_cfg_b: Any = None

        self._setup_ui()
        self._connect_signals()
        self.refresh_data()
        if os.environ.get("ANKIFORGE_ENV") == "testing":
            self._insert_mock_initial_data()

        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.setInterval(250)
        self._elapsed_timer.timeout.connect(self._on_elapsed_tick)

    def _build_inference_sliders(self, accent_color: str) -> tuple[QWidget, QSlider, QSlider]:
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

        lbl_temp_val = QLabel("0.70")
        lbl_temp_val.setStyleSheet(f"color: {accent_color}; font-size: 11px; font-weight: bold;")
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

        lbl_tok_val = QLabel("4096")
        lbl_tok_val.setStyleSheet(f"color: {accent_color}; font-size: 11px; font-weight: bold;")
        tok_slider.valueChanged.connect(lambda v, lbl=lbl_tok_val: lbl.setText(str(v)))

        adv_layout.addWidget(lbl_tok)
        adv_layout.addWidget(tok_slider)
        adv_layout.addWidget(lbl_tok_val)
        adv_layout.addStretch()

        return adv_widget, temp_slider, tok_slider

    def _load_ab_settings(self) -> None:
        """Restaure les réglages inférence (globaux et par branche) depuis SettingsService."""
        temp_int = int(SettingsService.get("ab_test/global_temperature", 70))
        tok_int = int(SettingsService.get("ab_test/global_max_tokens", 4096))
        self.global_temp_slider.blockSignals(True)
        self.global_tok_slider.blockSignals(True)
        self.global_temp_slider.setValue(max(0, min(200, temp_int)))
        self.global_tok_slider.setValue(max(256, min(8192, tok_int)))
        self.global_temp_slider.blockSignals(False)
        self.global_tok_slider.blockSignals(False)

        for slider, key, min_val, max_val in (
            (self.temp_slider_a, "ab_test/temperature_a", 0, 200),
            (self.tok_slider_a, "ab_test/max_tokens_a", 256, 8192),
            (self.temp_slider_b, "ab_test/temperature_b", 0, 200),
            (self.tok_slider_b, "ab_test/max_tokens_b", 256, 8192),
        ):
            val = int(SettingsService.get(key, slider.value()))
            slider.blockSignals(True)
            slider.setValue(max(min_val, min(max_val, val)))
            slider.blockSignals(False)

    def _persist_slider(self, key: str, value: int) -> None:
        SettingsService.set(key, int(value), category="ab_test")

    def _on_independent_settings_changed(self) -> None:
        independent = self.chk_independent.isChecked()
        SettingsService.set("ab_test/independent_settings", independent, category="ab_test")
        for slider in (self.temp_slider_a, self.tok_slider_a, self.temp_slider_b, self.tok_slider_b):
            slider.setEnabled(independent)
        self.global_adv_widget.setVisible(not independent)
        self.adv_branch_a_widget.setVisible(independent)
        self.adv_branch_b_widget.setVisible(independent)

    def _effective_temperature(self, branch: str) -> float | None:
        if self.chk_independent.isChecked():
            slider = self.temp_slider_a if branch == "A" else self.temp_slider_b
            return slider.value() / 100
        return self.global_temp_slider.value() / 100

    def _effective_max_tokens(self, branch: str) -> int | None:
        if self.chk_independent.isChecked():
            slider = self.tok_slider_a if branch == "A" else self.tok_slider_b
            return slider.value()
        return self.global_tok_slider.value()

    def _setup_ui(self) -> None:
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.ab_panel = IdePanel(detachable=True)
        self.ab_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        ab_content = QWidget()
        ab_layout = QVBoxLayout(ab_content)
        ab_layout.setContentsMargins(12, 12, 12, 12)
        ab_layout.setSpacing(10)

        # ── ÉCRANS 1 & 2 (Config → Résultats) via progressive disclosure ────────
        self.phase_stack = QStackedWidget()
        self.config_page = QWidget()
        config_layout = QVBoxLayout(self.config_page)
        config_layout.setContentsMargins(0, 0, 0, 0)
        config_layout.setSpacing(10)

        self.results_page = QWidget()
        results_layout = QVBoxLayout(self.results_page)
        results_layout.setContentsMargins(0, 0, 0, 0)
        results_layout.setSpacing(10)

        # ── 1. ÉCRAN CONFIGURATION : SPLITTER SOURCE | PARAMÈTRES ─────────────
        self.config_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.config_splitter.setChildrenCollapsible(False)
        self.config_splitter.setStyleSheet(f"""
            QSplitter::handle {{
                background-color: {DesignTokens.BORDER_COLOR};
                width: 3px;
                border-radius: 1px;
            }}
            QSplitter::handle:hover {{
                background-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)

        # ── 1a. COLONNE GAUCHE : TEXTE SOURCE (pleine hauteur) ────────────────
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

        lbl_presets = QLabel("Source :")
        lbl_presets.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10.5px; font-weight: 500;")
        src_header.addWidget(lbl_presets, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.doc_picker = DocumentPickerButton(allow_clear=True)
        src_header.addWidget(self.doc_picker, alignment=Qt.AlignmentFlag.AlignVCenter)

        src_header.addStretch()

        btn_clear_src = IconButton("ph.trash", tooltip="Effacer le texte source", size=22)
        btn_clear_src.clicked.connect(self._on_clear_source)
        src_header.addWidget(btn_clear_src, alignment=Qt.AlignmentFlag.AlignVCenter)

        source_layout.addLayout(src_header)

        self.source_editor.setMinimumHeight(260)
        self.source_editor.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.source_editor.btn_generate.hide()
        source_layout.addWidget(self.source_editor, 1)

        # ── 1b. COLONNE DROITE : PARAMÈTRES DU TEST (panel vertical) ──────────
        self.config_panel = QFrame()
        self.config_panel.setObjectName("ConfigPanel")
        self._apply_config_panel_style()

        config_panel_layout = QVBoxLayout(self.config_panel)
        config_panel_layout.setContentsMargins(12, 10, 12, 10)
        config_panel_layout.setSpacing(10)

        # Section 1 : Configuration du test (Mode + Paquet Cible)
        block_test, box_test = self._build_config_block("CONFIGURATION DU TEST")
        test_rows = QVBoxLayout()
        test_rows.setContentsMargins(0, 0, 0, 0)
        test_rows.setSpacing(6)

        row_mode = QHBoxLayout()
        row_mode.setContentsMargins(0, 0, 0, 0)
        row_mode.setSpacing(8)
        lbl_mode = QLabel("Mode :")
        lbl_mode.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
        self.mode_combo = StyledComboBox()
        self.mode_combo.setMinimumWidth(190)
        self.mode_combo.setFixedHeight(30)
        self.mode_combo.addItem(load_phosphor_icon("ph.cpu", color=DesignTokens.ACCENT_PRIMARY), "Comparer deux Moteurs IA")
        self.mode_combo.addItem(load_phosphor_icon("ph.sparkle", color=DesignTokens.COLOR_YELLOW), "Comparer deux Prompts / Personas")
        self.mode_combo.addItem(load_phosphor_icon("ph.git-branch", color=DesignTokens.COLOR_GREEN), "Comparer deux Pipelines DAG")
        self.mode_combo.setSizeAdjustPolicy(StyledComboBox.SizeAdjustPolicy.AdjustToContents)
        row_mode.addWidget(lbl_mode, alignment=Qt.AlignmentFlag.AlignVCenter)
        row_mode.addWidget(self.mode_combo, 1)
        test_rows.addLayout(row_mode)

        row_deck = QHBoxLayout()
        row_deck.setContentsMargins(0, 0, 0, 0)
        row_deck.setSpacing(8)
        lbl_deck = QLabel("Paquet Cible :")
        lbl_deck.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
        self.deck_combo = StyledComboBox()
        self.deck_combo.setMinimumWidth(130)
        self.deck_combo.setFixedHeight(30)
        row_deck.addWidget(lbl_deck, alignment=Qt.AlignmentFlag.AlignVCenter)
        row_deck.addWidget(self.deck_combo, 1)
        test_rows.addLayout(row_deck)

        box_test.addLayout(test_rows)
        config_panel_layout.addWidget(block_test)

        # Section 2 : Paramètres d'évaluation (Agent/Moteur Commun + Modèle Cible)
        block_eval, box_eval = self._build_config_block("PARAMÈTRES D'ÉVALUATION")
        eval_rows = QVBoxLayout()
        eval_rows.setContentsMargins(0, 0, 0, 0)
        eval_rows.setSpacing(6)

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
        gp_layout.addWidget(self.persona_combo, 1)
        eval_rows.addWidget(self.global_persona_widget)

        self.global_engine_widget = QWidget()
        ge_layout = QHBoxLayout(self.global_engine_widget)
        ge_layout.setContentsMargins(0, 0, 0, 0)
        ge_layout.setSpacing(6)
        lbl_ge = QLabel("Moteur Commun :")
        lbl_ge.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
        self.global_engine_combo = ModelSelectorWidget(allow_inherit=False, show_badges=False, parent=self)
        self.global_engine_combo.setMinimumWidth(180)
        ge_layout.addWidget(lbl_ge)
        ge_layout.addWidget(self.global_engine_combo, 1)
        eval_rows.addWidget(self.global_engine_widget)
        self.global_engine_widget.hide()

        row_nt = QHBoxLayout()
        row_nt.setContentsMargins(0, 0, 0, 0)
        row_nt.setSpacing(8)
        lbl_nt = QLabel("Modèle Cible :")
        lbl_nt.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
        self.model_combo = StyledComboBox()
        self.model_combo.setMinimumWidth(150)
        self.model_combo.setFixedHeight(30)
        row_nt.addWidget(lbl_nt, alignment=Qt.AlignmentFlag.AlignVCenter)
        row_nt.addWidget(self.model_combo, 1)
        eval_rows.addLayout(row_nt)

        box_eval.addLayout(eval_rows)
        config_panel_layout.addWidget(block_eval)

        # Section 3 : Branches à comparer (ce qui est réellement testé : Moteur / Prompt / Pipeline)
        self.branches_block, branches_box = self._build_config_block("BRANCHES À COMPARER")
        branches_rows = QVBoxLayout()
        branches_rows.setContentsMargins(0, 0, 0, 0)
        branches_rows.setSpacing(6)

        row_branch_a = QHBoxLayout()
        row_branch_a.setContentsMargins(0, 0, 0, 0)
        row_branch_a.setSpacing(8)
        self.lbl_a = QLabel("Moteur A :")
        self.lbl_a.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
        self.engine_a_combo = ModelSelectorWidget(allow_inherit=False, show_badges=False, parent=self)
        self.persona_a_combo = StyledComboBox()
        self.persona_a_combo.setFixedHeight(30)
        self.persona_a_combo.hide()
        self.pipeline_a_combo = StyledComboBox()
        self.pipeline_a_combo.setFixedHeight(30)
        self.pipeline_a_combo.hide()
        row_branch_a.addWidget(self.lbl_a, alignment=Qt.AlignmentFlag.AlignVCenter)
        row_branch_a.addWidget(self.engine_a_combo, 1)
        row_branch_a.addWidget(self.persona_a_combo, 1)
        row_branch_a.addWidget(self.pipeline_a_combo, 1)
        branches_rows.addLayout(row_branch_a)

        row_branch_b = QHBoxLayout()
        row_branch_b.setContentsMargins(0, 0, 0, 0)
        row_branch_b.setSpacing(8)
        self.lbl_b = QLabel("Moteur B :")
        self.lbl_b.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
        self.engine_b_combo = ModelSelectorWidget(allow_inherit=False, show_badges=False, parent=self)
        self.persona_b_combo = StyledComboBox()
        self.persona_b_combo.setFixedHeight(30)
        self.persona_b_combo.hide()
        self.pipeline_b_combo = StyledComboBox()
        self.pipeline_b_combo.setFixedHeight(30)
        self.pipeline_b_combo.hide()
        row_branch_b.addWidget(self.lbl_b, alignment=Qt.AlignmentFlag.AlignVCenter)
        row_branch_b.addWidget(self.engine_b_combo, 1)
        row_branch_b.addWidget(self.persona_b_combo, 1)
        row_branch_b.addWidget(self.pipeline_b_combo, 1)
        branches_rows.addLayout(row_branch_b)

        branches_box.addLayout(branches_rows)
        config_panel_layout.addWidget(self.branches_block)

        # Section 4 : Réglages Inférence (toujours visibles)
        block_inf, box_inf = self._build_config_block("RÉGLAGES INFÉRENCE")
        inf_rows = QVBoxLayout()
        inf_rows.setContentsMargins(0, 0, 0, 0)
        inf_rows.setSpacing(6)

        self.global_adv_widget, self.global_temp_slider, self.global_tok_slider = self._build_inference_sliders(DesignTokens.ACCENT_PRIMARY)
        self.adv_branch_a_widget, self.temp_slider_a, self.tok_slider_a = self._build_inference_sliders(DesignTokens.BRANCH_A)
        self.adv_branch_b_widget, self.temp_slider_b, self.tok_slider_b = self._build_inference_sliders(DesignTokens.BRANCH_B)

        self.chk_independent = QCheckBox("Réglages indépendants A/B")
        self.chk_independent.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_independent.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11.5px; font-weight: 500;")
        self.chk_independent.setChecked(bool(SettingsService.get("ab_test/independent_settings", False)))
        self.chk_independent.stateChanged.connect(self._on_independent_settings_changed)

        inf_rows.addWidget(self.global_adv_widget)
        inf_rows.addWidget(self.chk_independent)
        inf_rows.addWidget(self.adv_branch_a_widget)
        inf_rows.addWidget(self.adv_branch_b_widget)
        box_inf.addLayout(inf_rows)
        config_panel_layout.addWidget(block_inf)

        config_panel_layout.addStretch(1)

        self.btn_run = PrimaryButton("Lancer le Test A/B", tooltip="Lancer le test comparatif A/B sur les deux configurations (Ctrl+Entrée)")
        self.btn_run.setIcon(load_on_accent_icon("ph.play"))
        self.btn_run.setIconSize(QSize(15, 15))
        self.btn_run.setFixedHeight(34)
        self.btn_run.setMinimumWidth(200)
        apply_shadow(self.btn_run, blur=14, offset_y=0, color="rgba(99, 102, 241, 0.7)")
        config_panel_layout.addWidget(self.btn_run)

        self._load_ab_settings()
        self._on_independent_settings_changed()

        self.config_splitter.addWidget(self.source_box)
        self.config_splitter.addWidget(self.config_panel)
        self.config_splitter.setStretchFactor(0, 55)
        self.config_splitter.setStretchFactor(1, 45)
        config_layout.addWidget(self.config_splitter, 1)

        # ── 2. BARRE DE RÉSUMÉ DE CONFIGURATION (ÉCRAN RÉSULTATS) ─────────────
        self.config_summary_bar = QFrame()
        self.config_summary_bar.setObjectName("ConfigSummaryBar")
        self.config_summary_bar.setMinimumHeight(40)
        self._apply_summary_bar_style()

        summary_vbox = QVBoxLayout(self.config_summary_bar)
        summary_vbox.setContentsMargins(12, 6, 12, 6)
        summary_vbox.setSpacing(4)

        summary_top = QHBoxLayout()
        summary_top.setSpacing(8)

        self.btn_back = SecondaryButton("Modifier la configuration")
        self.btn_back.setIcon(load_phosphor_icon("ph.arrow-left", color=DesignTokens.TEXT_PRIMARY))
        self.btn_back.setFixedHeight(28)
        self.btn_back.clicked.connect(self._show_config_page)
        summary_top.addWidget(self.btn_back, alignment=Qt.AlignmentFlag.AlignVCenter)

        lbl_summary_title = QLabel("RÉSUMÉ DE LA CONFIGURATION :")
        lbl_summary_title.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        summary_top.addWidget(lbl_summary_title, alignment=Qt.AlignmentFlag.AlignVCenter)

        summary_top.addStretch()

        self.summary_badges = QWidget()
        self.summary_badges.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        badges_flow = FlowLayout(self.summary_badges, margin=0, h_spacing=6, v_spacing=4)
        for key in ("mode", "deck", "model", "branch_a", "branch_b", "inf_a", "inf_b"):
            self.summary_labels[key] = self._make_summary_badge("—")
            badges_flow.addWidget(self.summary_labels[key])

        summary_vbox.addLayout(summary_top)
        summary_vbox.addWidget(self.summary_badges)

        results_layout.addWidget(self.config_summary_bar)

        # ── 3. BARRE CENTRALE DE COMMUTATION DE REPRÉSENTATION ─────────────────
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

        self.btn_subtab_diff = SubTabButton("Diff A↔B", "ph.git-diff", is_active=False)
        self.btn_subtab_diff.clicked.connect(lambda: self._switch_view_mode(3))
        switcher_bar.addWidget(self.btn_subtab_diff, alignment=Qt.AlignmentFlag.AlignVCenter)

        switcher_bar.addStretch()

        self.chk_sync_nav = QCheckBox("Synchronisation Navigation A ↔ B")
        self.chk_sync_nav.setChecked(bool(SettingsService.get("ab_test/sync_nav", True)))
        self.chk_sync_nav.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_sync_nav.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px; font-weight: 500;")
        self.chk_sync_nav.stateChanged.connect(lambda s: SettingsService.set("ab_test/sync_nav", s == Qt.CheckState.Checked.value, category="ab_test"))
        switcher_bar.addWidget(self.chk_sync_nav, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.btn_device_desktop = IconButton("ph.monitor", tooltip="Mode Bureau (100% largeur)", size=24)
        self.btn_device_desktop.clicked.connect(lambda: self._set_both_device_mode("desktop"))
        switcher_bar.addWidget(self.btn_device_desktop, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.btn_device_tablet = IconButton("ph.device-tablet", tooltip="Mode Tablette (768px)", size=24)
        self.btn_device_tablet.clicked.connect(lambda: self._set_both_device_mode("tablet"))
        switcher_bar.addWidget(self.btn_device_tablet, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.btn_device_mobile = IconButton("ph.device-mobile", tooltip="Mode Mobile (375px)", size=24)
        self.btn_device_mobile.clicked.connect(lambda: self._set_both_device_mode("mobile"))
        switcher_bar.addWidget(self.btn_device_mobile, alignment=Qt.AlignmentFlag.AlignVCenter)

        results_layout.addLayout(switcher_bar)

        # ── 4. COMPARATIF CÔTE-À-CÔTE (BRANCHE A VS BRANCHE B) ─────────────────
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
        results_layout.addWidget(self.compare_splitter, 1)

        # ── PANNEAU A ──
        self.panel_a = QFrame()
        self.panel_a.setObjectName("PanelA")
        layout_a = QVBoxLayout(self.panel_a)
        layout_a.setContentsMargins(10, 10, 10, 10)
        layout_a.setSpacing(8)

        toolbar_a = QHBoxLayout()
        toolbar_a.setContentsMargins(0, 0, 0, 0)
        toolbar_a.setSpacing(8)

        self.lbl_branch_a = QLabel("—")
        self.lbl_branch_a.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11px; font-weight: 600;")
        self.lbl_branch_a.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        self.btn_flip_a = SecondaryButton("Voir Verso")
        self.btn_flip_a.setIcon(load_phosphor_icon("ph.eye", color=DesignTokens.TEXT_PRIMARY))
        self.btn_flip_a.setFixedHeight(26)
        self.btn_flip_a.setToolTip("Basculer Recto/Verso de la Branche A")

        toolbar_a.addWidget(self.lbl_branch_a, 1, alignment=Qt.AlignmentFlag.AlignVCenter)
        toolbar_a.addWidget(self.btn_flip_a, alignment=Qt.AlignmentFlag.AlignVCenter)
        layout_a.addLayout(toolbar_a)

        self.kpi_a = BranchKpiWidget("BRANCHE A", color_hex=DesignTokens.BRANCH_A)
        self.kpi_a.set_idle()
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
        self.diff_a = DiffViewerWidget()
        self.stack_a.addWidget(self.diff_a)
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

        self.lbl_branch_b = QLabel("—")
        self.lbl_branch_b.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11px; font-weight: 600;")
        self.lbl_branch_b.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        self.btn_flip_b = SecondaryButton("Voir Verso")
        self.btn_flip_b.setIcon(load_phosphor_icon("ph.eye", color=DesignTokens.TEXT_PRIMARY))
        self.btn_flip_b.setFixedHeight(26)
        self.btn_flip_b.setToolTip("Basculer Recto/Verso de la Branche B")

        toolbar_b.addWidget(self.lbl_branch_b, 1, alignment=Qt.AlignmentFlag.AlignVCenter)
        toolbar_b.addWidget(self.btn_flip_b, alignment=Qt.AlignmentFlag.AlignVCenter)
        layout_b.addLayout(toolbar_b)

        self.kpi_b = BranchKpiWidget("BRANCHE B", color_hex=DesignTokens.BRANCH_B)
        self.kpi_b.set_idle()
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
        self.diff_b = DiffViewerWidget()
        self.stack_b.addWidget(self.diff_b)
        layout_b.addWidget(self.stack_b, 1)

        self.compare_splitter.addWidget(self.panel_b)
        self.compare_splitter.setSizes([500, 500])
        self.compare_splitter.setChildrenCollapsible(False)

        # ── 5. BARRE DE PAGINATION INTÉGRÉE ──────────────────────────────────
        pagination_bar = QHBoxLayout()
        pagination_bar.setContentsMargins(10, 4, 10, 4)
        pagination_bar.setSpacing(12)

        nav_a_box = QHBoxLayout()
        nav_a_box.setSpacing(6)
        lbl_pag_a = QLabel("Branche A :")
        lbl_pag_a.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
        self.btn_prev_a = IconButton("ph.caret-left", tooltip="Carte précédente (Branche A)", size=22)
        self.lbl_count_a = QLabel("0 / 0")
        self.lbl_count_a.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-family: '{DesignTokens.FONT_CODE}'; font-size: 11px; font-weight: bold;")
        self.btn_next_a = IconButton("ph.caret-right", tooltip="Carte suivante (Branche A)", size=22)
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
        self.btn_prev_b = IconButton("ph.caret-left", tooltip="Carte précédente (Branche B)", size=22)
        self.lbl_count_b = QLabel("0 / 0")
        self.lbl_count_b.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-family: '{DesignTokens.FONT_CODE}'; font-size: 11px; font-weight: bold;")
        self.btn_next_b = IconButton("ph.caret-right", tooltip="Carte suivante (Branche B)", size=22)
        nav_b_box.addWidget(lbl_pag_b)
        nav_b_box.addWidget(self.btn_prev_b)
        nav_b_box.addWidget(self.lbl_count_b)
        nav_b_box.addWidget(self.btn_next_b)
        pagination_bar.addLayout(nav_b_box)

        results_layout.addLayout(pagination_bar)

        # ── EMPILEMENT DES 2 PHASES ─────────────────────────────────────────────
        self.phase_stack.addWidget(self.config_page)
        self.phase_stack.addWidget(self.results_page)
        ab_layout.addWidget(self.phase_stack, 1)

        self._apply_theme_to_widgets()

        self.preview_a.set_empty_state("Branche A en attente. Configurez les options et cliquez sur 'Lancer le Test A/B'.")
        self.preview_b.set_empty_state("Branche B en attente. Configurez les options et cliquez sur 'Lancer le Test A/B'.")

        self.ab_panel.add_tab("Laboratoire A/B", ab_content, "ph.scales", closable=False)
        main_layout.addWidget(self.ab_panel, 1)

        shortcut_run = QShortcut(QKeySequence("Ctrl+Return"), self)
        shortcut_run.activated.connect(self._on_run_ab_test)

    def _build_config_block(self, title: str) -> tuple[QFrame, QHBoxLayout]:
        """Construit un bloc de configuration labelisé (fond bg_input, en-tête muted)."""
        frame = QFrame()
        frame.setObjectName("ConfigBlock")
        frame.setStyleSheet(f"""
            QFrame#ConfigBlock {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
            QFrame#ConfigBlock QLabel {{
                background: transparent;
            }}
        """)
        block_v = QVBoxLayout(frame)
        block_v.setContentsMargins(10, 6, 10, 6)
        block_v.setSpacing(4)

        lbl_title = QLabel(title)
        lbl_title.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        block_v.addWidget(lbl_title)

        box = QHBoxLayout()
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(8)
        block_v.addLayout(box)
        return frame, box

    def _apply_config_panel_style(self) -> None:
        self.config_panel.setStyleSheet(f"""
            QFrame#ConfigPanel {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
            QFrame#ConfigPanel QLabel {{
                background: transparent;
            }}
        """)

    def _apply_summary_bar_style(self) -> None:
        self.config_summary_bar.setStyleSheet(f"""
            QFrame#ConfigSummaryBar {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-bottom: 2px solid {DesignTokens.ACCENT_PRIMARY};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
            QFrame#ConfigSummaryBar QLabel {{
                background: transparent;
            }}
        """)

    def _make_summary_badge(self, text: str) -> QLabel:
        badge = QLabel(text)
        badge.setStyleSheet(f"""
            QLabel {{
                background-color: {DesignTokens.BG_INPUT};
                color: {DesignTokens.TEXT_SECONDARY};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 9999px;
                padding: 2px 10px;
                font-size: 10.5px;
                font-family: '{DesignTokens.FONT_CODE}';
                font-weight: 600;
            }}
        """)
        return badge

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
        self._apply_config_panel_style()
        self._apply_source_box_style()
        self._apply_summary_bar_style()

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
                font-family: '{DesignTokens.FONT_CODE}';
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

        for slider, key in (
            (self.global_temp_slider, "ab_test/global_temperature"),
            (self.global_tok_slider, "ab_test/global_max_tokens"),
            (self.temp_slider_a, "ab_test/temperature_a"),
            (self.tok_slider_a, "ab_test/max_tokens_a"),
            (self.temp_slider_b, "ab_test/temperature_b"),
            (self.tok_slider_b, "ab_test/max_tokens_b"),
        ):
            slider.valueChanged.connect(lambda v, k=key: self._persist_slider(k, v))

        self.chk_independent.stateChanged.connect(self._on_independent_settings_changed)

        self.btn_back.clicked.connect(self._show_config_page)
        self.btn_flip_a.clicked.connect(lambda: self.preview_a.flip_card())
        self.btn_flip_b.clicked.connect(lambda: self.preview_b.flip_card())
        self.doc_picker.document_changed.connect(self._on_document_changed)

    def _on_document_changed(self, doc: DocumentModel | None) -> None:
        """Réagit au changement de document source sélectionné via DocumentPickerButton."""
        if doc is None:
            self.source_editor.set_document(None)
            return
        self._apply_document_to_source(doc)

    def _on_clear_source(self) -> None:
        """Efface le texte source : désélectionne le document lié et vide l'éditeur."""
        self.doc_picker.clear_document()
        self.source_editor.set_content("")
        show_toast(self, "Texte source effacé.")

    def _apply_document_to_source(self, doc: DocumentModel) -> None:
        """Envoie le contenu du document sélectionné dans le texte source (vues PDF/Stylisé/Source)."""
        content = getattr(doc, "content", "") or getattr(doc, "text_content", "") or ""
        if not content:
            show_toast(self, f"Le document « {doc.title} » est vide.", is_error=True)
            return
        self.source_editor.set_document(doc)
        show_toast(self, f"Document « {doc.title} » importé (vues PDF/Stylisé/Source disponibles).")

    def _branch_display(self, branch: str) -> str:
        mode_idx = self.mode_combo.currentIndex()
        if mode_idx == 0:
            cfg = self.engine_a_combo.currentData() if branch == "A" else self.engine_b_combo.currentData()
        elif mode_idx == 1:
            cfg = self.persona_a_combo.currentData() if branch == "A" else self.persona_b_combo.currentData()
        else:
            cfg = self.pipeline_a_combo.currentData() if branch == "A" else self.pipeline_b_combo.currentData()
        if cfg is None:
            return "—"
        display = getattr(cfg, "name", None) or getattr(cfg, "display_name", None) or getattr(cfg, "model_id", None) or "—"
        return str(display)

    def _elide_badge(self, text: str, max_w: int = 220) -> str:
        """Tronque le texte d'un badge pour qu'il tienne dans FlowLayout sans écrasement."""
        return QFontMetrics(self.summary_labels["mode"].font()).elidedText(text, Qt.TextElideMode.ElideRight, max_w)

    def _update_results_branch_labels(self) -> None:
        """Affiche sur les toolbars Résultats la branche A/B réellement configurée (lecture seule)."""
        prefix = {0: "Moteur", 1: "Prompt", 2: "Pipeline"}.get(self.mode_combo.currentIndex(), "Moteur")
        self.lbl_branch_a.setText(self._elide_badge(f"{prefix} A : {self._branch_display('A')}"))
        self.lbl_branch_b.setText(self._elide_badge(f"{prefix} B : {self._branch_display('B')}"))

    def _update_config_summary(self) -> None:
        """Met à jour les badges de résumé de configuration affichés sur l'écran Résultats."""
        deck = self.deck_combo.currentData()
        nt = self.model_combo.currentData()
        deck_name = getattr(deck, "name", "—") if deck is not None else "—"
        nt_name = getattr(nt, "name", "—") if nt is not None else "—"
        temp_a = self._effective_temperature("A")
        tok_a = self._effective_max_tokens("A")
        temp_b = self._effective_temperature("B")
        tok_b = self._effective_max_tokens("B")
        fmt_temp = "—" if temp_a is None else f"{temp_a:.2f}"
        fmt_temp_b = "—" if temp_b is None else f"{temp_b:.2f}"
        fmt_tok = "—" if tok_a is None else str(int(tok_a))
        fmt_tok_b = "—" if tok_b is None else str(int(tok_b))
        self.summary_labels["mode"].setText(self._elide_badge(f"Mode : {self.mode_combo.currentText()}"))
        self.summary_labels["deck"].setText(self._elide_badge(f"Deck : {deck_name}"))
        self.summary_labels["model"].setText(self._elide_badge(f"Modèle : {nt_name}"))
        self.summary_labels["branch_a"].setText(self._elide_badge(f"A : {self._branch_display('A')}"))
        self.summary_labels["branch_b"].setText(self._elide_badge(f"B : {self._branch_display('B')}"))
        self.summary_labels["inf_a"].setText(self._elide_badge(f"IA : {fmt_temp} / {fmt_tok}"))
        self.summary_labels["inf_b"].setText(self._elide_badge(f"IB : {fmt_temp_b} / {fmt_tok_b}"))
        self._update_results_branch_labels()

    def _switch_view_mode(self, mode_idx: int) -> None:
        self.btn_subtab_preview.set_active(mode_idx == 0)
        self.btn_subtab_table.set_active(mode_idx == 1)
        self.btn_subtab_json.set_active(mode_idx == 2)
        self.btn_subtab_diff.set_active(mode_idx == 3)
        self.stack_a.setCurrentIndex(mode_idx)
        self.stack_b.setCurrentIndex(mode_idx)

        # Le flip Recto/Verso n'a de sens qu'en Rendu Visuel
        is_preview = mode_idx == 0
        self.btn_flip_a.setVisible(is_preview)
        self.btn_flip_b.setVisible(is_preview)

    def _show_config_page(self) -> None:
        """Retour à l'écran de configuration (les résultats sont préservés)."""
        self.phase_stack.setCurrentWidget(self.config_page)

    def _show_results_page(self) -> None:
        """Bascule sur l'écran de résultats (lancé automatiquement en fin de config)."""
        self.phase_stack.setCurrentWidget(self.results_page)

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
            self.engine_a_combo.refresh_models()
            self.engine_b_combo.refresh_models()
            self.global_engine_combo.refresh_models()
            if self.engine_b_combo.count() > 1:
                self.engine_b_combo.setCurrentIndex(1)

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
        _mock_source = (
            "L'insuffisance cardiaque droite est caractérisée par l'incapacité du ventricule droit "
            "à assurer un débit sanguin pulmonaire suffisant. Les signes cliniques prédominants "
            "associent turgescence jugulaire, reflux hépato-jugulaire, hépatomégalie douloureuse "
            "et œdèmes des membres inférieurs."
        )
        self.source_editor.set_content(_mock_source)

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
                pass

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

        # Diff A ↔ B (4e niveau)
        if self.cards_a and self.cards_b:
            card_a = self.cards_a[self.index_a]
            card_b = self.cards_b[self.index_b]
            self.diff_a.set_content_diff(card_a, card_b)
            self.diff_b.set_content_diff(card_b, card_a)
        else:
            self.diff_a.setHtml("<p style='color:#94a3b8;'>En attente des cartes des deux branches pour générer le diff.</p>")
            self.diff_b.setHtml("<p style='color:#94a3b8;'>En attente des cartes des deux branches pour générer le diff.</p>")

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
        text_source = self.source_editor.get_text()
        if not text_source:
            show_toast(self, "Veuillez saisir un texte source à tester.", is_error=True)
            return

        selected_nt = self.model_combo.currentData()
        nt_id = selected_nt.id if selected_nt and hasattr(selected_nt, "id") else 1
        nt_schema = json.loads(selected_nt.fields_schema) if selected_nt and selected_nt.fields_schema else ["Front", "Back"]

        mode_idx = self.mode_combo.currentIndex()

        temp_a = self._effective_temperature("A")
        tok_a = self._effective_max_tokens("A")
        temp_b = self._effective_temperature("B")
        tok_b = self._effective_max_tokens("B")

        inf_cfg_a: dict[str, Any] = {}
        if temp_a is not None:
            inf_cfg_a["temperature"] = temp_a
        if tok_a is not None:
            inf_cfg_a["max_tokens"] = tok_a
        inf_cfg_b: dict[str, Any] = {}
        if temp_b is not None:
            inf_cfg_b["temperature"] = temp_b
        if tok_b is not None:
            inf_cfg_b["max_tokens"] = tok_b

        steps_a = None
        steps_b = None
        self._persona_cfg_a = None
        self._persona_cfg_b = None
        self._pipeline_cfg_a = None
        self._pipeline_cfg_b = None

        if mode_idx == 0:
            engine_a = self.engine_a_combo.currentData()
            engine_b = self.engine_b_combo.currentData()
            pipe_id_a = None
            pipe_id_b = None
            common_persona = self.persona_combo.currentData()
            if common_persona:
                steps_a = [PipelineStepModel(persona=common_persona, step_type="LLM_PROMPT", step_order=1, config_data=json.dumps(inf_cfg_a))]
                steps_b = [PipelineStepModel(persona=common_persona, step_type="LLM_PROMPT", step_order=1, config_data=json.dumps(inf_cfg_b))]

        elif mode_idx == 1:
            engine_a = self.global_engine_combo.currentData()
            engine_b = self.global_engine_combo.currentData()
            pipe_id_a = None
            pipe_id_b = None
            p_a = self.persona_a_combo.currentData()
            p_b = self.persona_b_combo.currentData()
            self._persona_cfg_a = p_a
            self._persona_cfg_b = p_b
            if p_a:
                steps_a = [PipelineStepModel(persona=p_a, step_type="LLM_PROMPT", step_order=1, config_data=json.dumps(inf_cfg_a))]
            if p_b:
                steps_b = [PipelineStepModel(persona=p_b, step_type="LLM_PROMPT", step_order=1, config_data=json.dumps(inf_cfg_b))]

        else:
            engine_a = self.global_engine_combo.currentData()
            engine_b = self.global_engine_combo.currentData()
            pipe_a = self.pipeline_a_combo.currentData()
            pipe_b = self.pipeline_b_combo.currentData()
            self._pipeline_cfg_a = pipe_a
            self._pipeline_cfg_b = pipe_b
            pipe_id_a = pipe_a.id if pipe_a else None
            pipe_id_b = pipe_b.id if pipe_b else None

        show_toast(self, "Lancement du test A/B en parallèle via le Moteur DAG...")
        self._update_config_summary()
        self._show_results_page()
        self.btn_run.setEnabled(False)
        self._completed_a = False
        self._completed_b = False
        self.preview_a.set_empty_state("Branche A : test en cours... Les résultats s'afficheront ici.")
        self.preview_b.set_empty_state("Branche B : test en cours... Les résultats s'afficheront ici.")
        self.kpi_a.set_running()
        self.kpi_b.set_running()
        self._elapsed_timer.start()

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
        if temp_a is not None:
            state_a.set_variable("temperature", temp_a)
        if tok_a is not None:
            state_a.set_variable("max_tokens", tok_a)

        state_b = PipelineRunState(initial_prompt=text_source[:120])
        state_b.set_variable("text_source", text_source)
        state_b.set_variable("fields", nt_schema)
        state_b.set_variable("note_type_id", nt_id)
        if temp_b is not None:
            state_b.set_variable("temperature", temp_b)
        if tok_b is not None:
            state_b.set_variable("max_tokens", tok_b)

        self._engine_cfg_a = engine_a
        self._engine_cfg_b = engine_b
        self._start_time_a = time.perf_counter()
        self._start_time_b = time.perf_counter()
        self._ab_run_id = uuid.uuid4().hex

        self.orchestrator_a = PipelineOrchestrator(
            pipeline_id=pipe_id_a,
            initial_state=state_a,
            steps=steps_a,
            ai_provider=provider_a,
            ab_run_id=f"{self._ab_run_id}:A",
        )
        self.orchestrator_a.signals.pipeline_finished.connect(self._on_finished_a)
        self.orchestrator_a.signals.error_occurred.connect(lambda err: self._on_error_a(err))

        self.orchestrator_b = PipelineOrchestrator(
            pipeline_id=pipe_id_b,
            initial_state=state_b,
            steps=steps_b,
            ai_provider=provider_b,
            ab_run_id=f"{self._ab_run_id}:B",
        )
        self.orchestrator_b.signals.pipeline_finished.connect(self._on_finished_b)
        self.orchestrator_b.signals.error_occurred.connect(lambda err: self._on_error_b(err))

        QThreadPool.globalInstance().start(self.orchestrator_a)
        QThreadPool.globalInstance().start(self.orchestrator_b)

    def _on_elapsed_tick(self) -> None:
        if not self._completed_a:
            self.kpi_a.set_running_elapsed(time.perf_counter() - self._start_time_a)
        if not self._completed_b:
            self.kpi_b.set_running_elapsed(time.perf_counter() - self._start_time_b)

    def _extract_cards_from_state(self, state: PipelineRunState) -> list[dict[str, Any]]:
        raw_cards = state.get_variable("generated_cards") or state.get_variable("map_reduce_results") or state.get_variable("last_output") or []
        return extract_cards_from_data(raw_cards)

    def _prefer_measured_usage(self, ab_run_id: str, tokens_est: int, cost_est: float) -> tuple[int, float]:
        """Remplace l'estimation par la consommation réelle mesurée si elle est disponible."""
        if not self._ab_run_id:
            return tokens_est, cost_est
        try:
            from ankiforge.repositories.setting_repository import SettingRepository

            usage = SettingRepository().get_usage_for_ab_run(ab_run_id)
            if usage.get("total_calls"):
                return int(usage.get("total_tokens") or tokens_est), float(usage.get("total_cost_usd") or cost_est)
        except Exception as e:
            logger.debug("Lecture de la consommation réelle A/B impossible (%s) : %s", ab_run_id, e)
        return tokens_est, cost_est

    @Slot(object)
    def _on_finished_a(self, state: PipelineRunState) -> None:
        elapsed = time.perf_counter() - self._start_time_a
        self.cards_a = self._extract_cards_from_state(state)
        self.index_a = 0
        self._completed_a = True

        tokens_est = len(str(self.cards_a)) // 4
        _, cost_est = estimate_run_cost(tokens_est, tokens_est, self._engine_cfg_a)
        tokens_est, cost_est = self._prefer_measured_usage(f"{self._ab_run_id}:A", tokens_est, cost_est)
        self.kpi_a.set_results(elapsed=elapsed, cards_count=len(self.cards_a), tokens=tokens_est, cost_usd=cost_est, is_success=True)

        if self._completed_b:
            self._elapsed_timer.stop()
        self._check_test_complete()

    @Slot(object)
    def _on_finished_b(self, state: PipelineRunState) -> None:
        elapsed = time.perf_counter() - self._start_time_b
        self.cards_b = self._extract_cards_from_state(state)
        self.index_b = 0
        self._completed_b = True

        tokens_est = len(str(self.cards_b)) // 4
        _, cost_est = estimate_run_cost(tokens_est, tokens_est, self._engine_cfg_b)
        tokens_est, cost_est = self._prefer_measured_usage(f"{self._ab_run_id}:B", tokens_est, cost_est)
        self.kpi_b.set_results(elapsed=elapsed, cards_count=len(self.cards_b), tokens=tokens_est, cost_usd=cost_est, is_success=True)

        if self._completed_a:
            self._elapsed_timer.stop()
        self._check_test_complete()

    def _on_error_a(self, err: str) -> None:
        elapsed = time.perf_counter() - self._start_time_a
        self._completed_a = True
        if self._completed_b:
            self._elapsed_timer.stop()
        self.kpi_a.set_results(elapsed=elapsed, cards_count=0, tokens=0, cost_usd=0.0, is_success=False, err_msg=err)
        show_toast(self, f"Erreur Branche A: {err}", is_error=True)
        self._check_test_complete()

    def _on_error_b(self, err: str) -> None:
        elapsed = time.perf_counter() - self._start_time_b
        self._completed_b = True
        if self._completed_a:
            self._elapsed_timer.stop()
        self.kpi_b.set_results(elapsed=elapsed, cards_count=0, tokens=0, cost_usd=0.0, is_success=False, err_msg=err)
        show_toast(self, f"Erreur Branche B: {err}", is_error=True)
        self._check_test_complete()

    def _check_test_complete(self) -> None:
        if self._completed_a and self._completed_b:
            self.btn_run.setEnabled(True)
            self._update_views()
            show_toast(self, "Test A/B terminé avec succès !")

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
                pass
        if hasattr(self, "orchestrator_b") and self.orchestrator_b is not None:
            try:
                self.orchestrator_b.cancel()
            except Exception:
                pass
        if hasattr(self, "preview_a") and self.preview_a is not None:
            try:
                self.preview_a.close()
            except Exception:
                pass
        if hasattr(self, "preview_b") and self.preview_b is not None:
            try:
                self.preview_b.close()
            except Exception:
                pass
        super().closeEvent(event)


ABTestsTab = ABTestsView

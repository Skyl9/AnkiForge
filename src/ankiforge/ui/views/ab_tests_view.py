"""
Vue Laboratoire A/B (Tests A/B) — Modernisée, Conforme au Design System et au Moteur DAG.

- Modes de Comparaison Multi-niveaux :
  * Mode 1 : Modèle vs Modèle (ex: GPT-4o vs Claude 3.5 Sonnet ou Ollama Local).
  * Mode 2 : Prompt vs Prompt (ex: Persona A vs Persona B sur le même moteur).
  * Mode 3 : Pipeline vs Pipeline (ex: Pipeline DAG A vs Pipeline DAG B).
- KPIs & Métriques Comparatives en Direct :
  * Durée d'exécution en secondes (⏱️).
  * Nombre de flashcards extraites (🃏).
  * Estimation des tokens et coût estimé (💰).
  * Statut de conformité du format JSON (🏷️).
- Vue Côte-à-Côte Symétrique (Splitter Branche A / Branche B) :
  * Onglet 1 : Rendu Visuel des Cartes (CardPreviewWidget avec gabarit NoteType).
  * Onglet 2 : Tableau Structuré des Champs (Clés/Valeurs).
  * Onglet 3 : JSON Brut formaté.
- Fonctionnalités Avancées :
  * Navigation synchronisée (A ↔ B) ou indépendante.
  * Bouton 'Importer dans la Forge' en 1-clic pour injecter les cartes gagnantes dans la base de données.
  * Exécution asynchrone multithread via deux instances concurrentes de PipelineOrchestrator dans QThreadPool.
"""

import json
import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, QThreadPool, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
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
from ankiforge.ui.components import (
    Badge,
    IconButton,
    IdePanel,
    PrimaryButton,
    SecondaryButton,
    StyledComboBox,
    StyledTextEdit,
)
from ankiforge.ui.components.tabs import IdeTabBar
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.card_preview_widget import CardPreviewWidget
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


def apply_pill_style(badge: QLabel, color_hex: str) -> None:
    """Applique un style de capsule/pill parfaitement arrondie avec fond translucide et bordure assortie."""
    hex_c = color_hex.lstrip("#")
    r, g, b = int(hex_c[0:2], 16), int(hex_c[2:4], 16), int(hex_c[4:6], 16)
    badge.setStyleSheet(f"""
        QLabel {{
            background-color: rgba({r}, {g}, {b}, 0.15) !important;
            color: {color_hex};
            border: 1px solid rgba({r}, {g}, {b}, 0.35);
            border-radius: 9999px;
            padding: 3px 12px;
            font-size: 10px;
            font-weight: bold;
            letter-spacing: 0.5px;
        }}
    """)


# =====================================================================
# COMPOSANT : BANNIÈRE DE MÉTRIQUES COMPARATIVES (KPIs)
# =====================================================================


class BranchKpiWidget(QFrame):
    """Affiche les métriques de performance d'une branche de test A/B."""

    def __init__(self, branch_title: str, color_hex: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.branch_title = branch_title
        self.color_hex = color_hex
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(12)

        # Badge Titre Branche
        self.badge_title = Badge(branch_title, variant="status")
        apply_pill_style(self.badge_title, color_hex)
        layout.addWidget(self.badge_title)

        # Durée
        self.lbl_time = QLabel("⏱️ 0.00s")
        self.lbl_time.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px; font-weight: bold;")
        layout.addWidget(self.lbl_time)

        # Cartes
        self.lbl_cards = QLabel("🃏 0 cartes")
        self.lbl_cards.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px; font-weight: bold;")
        layout.addWidget(self.lbl_cards)

        # Tokens
        self.lbl_tokens = QLabel("🪙 ~0 tok")
        self.lbl_tokens.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")
        layout.addWidget(self.lbl_tokens)

        # Coût estimé
        self.lbl_cost = QLabel("💰 $0.000")
        self.lbl_cost.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")
        layout.addWidget(self.lbl_cost)

        layout.addStretch()

        # Statut
        self.lbl_status = Badge("Prêt", variant="neutral")
        self.lbl_status.setStyleSheet(f"""
            QLabel {{
                background-color: {DesignTokens.BG_INPUT};
                color: {DesignTokens.TEXT_MUTED};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 9999px;
                padding: 2px 8px;
                font-size: 9px;
                font-weight: bold;
            }}
        """)
        layout.addWidget(self.lbl_status)

    def set_running(self) -> None:
        self.lbl_status.setText("⏳ En cours...")
        self.lbl_status.setStyleSheet("""
            QLabel {
                background-color: rgba(59, 130, 246, 0.2);
                color: #60a5fa;
                border: 1px solid #3b82f6;
                border-radius: 9999px;
                padding: 2px 8px;
                font-size: 9px;
                font-weight: bold;
            }
        """)

    def set_results(self, elapsed: float, cards_count: int, tokens: int, cost_usd: float, is_success: bool = True, err_msg: str = "") -> None:
        self.lbl_time.setText(f"⏱️ {elapsed:.2f}s")
        self.lbl_cards.setText(f"🃏 {cards_count} carte{'s' if cards_count > 1 else ''}")
        self.lbl_tokens.setText(f"🪙 ~{tokens} tok")
        self.lbl_cost.setText(f"💰 ${cost_usd:.4f}" if cost_usd > 0 else "💰 0€ (Local)")

        if is_success:
            self.lbl_status.setText("✅ Terminé")
            self.lbl_status.setStyleSheet("""
                QLabel {
                    background-color: rgba(16, 185, 129, 0.2);
                    color: #34d399;
                    border: 1px solid #10b981;
                    border-radius: 9999px;
                    padding: 2px 8px;
                    font-size: 9px;
                    font-weight: bold;
                }
            """)
        else:
            self.lbl_status.setText("❌ Erreur")
            self.lbl_status.setToolTip(err_msg)
            self.lbl_status.setStyleSheet("""
                QLabel {
                    background-color: rgba(239, 68, 68, 0.2);
                    color: #f87171;
                    border: 1px solid #ef4444;
                    border-radius: 9999px;
                    padding: 2px 8px;
                    font-size: 9px;
                    font-weight: bold;
                }
            """)


# =====================================================================
# VUE PRINCIPALE : LABORATOIRE DE TESTS A/B (ABTESTSVIEW)
# =====================================================================


class ABTestsView(QWidget):
    """
    Vue Laboratoire A/B — Comparateur haute précision de Moteurs, Prompts et Pipelines DAG.
    """

    def __init__(self, ai_manager: Optional[Any] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.ai_manager = ai_manager

        self.cards_a: List[Dict[str, Any]] = []
        self.index_a: int = 0

        self.cards_b: List[Dict[str, Any]] = []
        self.index_b: int = 0

        self.orchestrator_a: Optional[PipelineOrchestrator] = None
        self.orchestrator_b: Optional[PipelineOrchestrator] = None
        self._start_time_a: float = 0.0
        self._start_time_b: float = 0.0
        self._completed_a: bool = False
        self._completed_b: bool = False

        self._setup_ui()
        self._connect_signals()
        self.refresh_data()
        self._insert_mock_initial_data()

    def _build_advanced_settings(self) -> tuple[QWidget, QSlider, QSlider]:
        adv_widget = QWidget()
        adv_layout = QHBoxLayout(adv_widget)
        adv_layout.setContentsMargins(8, 2, 8, 2)
        adv_layout.setSpacing(14)

        lbl_temp = QLabel("Température :")
        lbl_temp.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")

        temp_slider = QSlider(Qt.Orientation.Horizontal)
        temp_slider.setRange(0, 200)
        temp_slider.setValue(70)
        temp_slider.setFixedWidth(100)

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
        lbl_tok.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")

        tok_slider = QSlider(Qt.Orientation.Horizontal)
        tok_slider.setRange(256, 8192)
        tok_slider.setValue(4096)
        tok_slider.setFixedWidth(100)
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
        main_layout.setSpacing(12)

        self.ab_panel = IdePanel(detachable=True)

        ab_content = QWidget()
        ab_layout = QVBoxLayout(ab_content)
        ab_layout.setContentsMargins(10, 10, 10, 10)
        ab_layout.setSpacing(10)

        # ── 1. BARRE DE CONFIGURATION SUPÉRIEURE ──────────────────────────────
        config_bar_widget = QWidget()
        config_bar_widget.setObjectName("ConfigBarWidget")
        config_bar_widget.setStyleSheet(
            f"QWidget#ConfigBarWidget {{ background-color: {DesignTokens.BG_INPUT}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: {DesignTokens.RADIUS_MD}px; }}"
        )
        config_bar = QHBoxLayout(config_bar_widget)
        config_bar.setContentsMargins(10, 8, 10, 8)
        config_bar.setSpacing(10)

        # Sélecteur de Mode
        lbl_mode = QLabel("MODE DE TEST :")
        lbl_mode.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        config_bar.addWidget(lbl_mode)

        self.mode_combo = StyledComboBox()
        self.mode_combo.addItems(
            [
                "🤖 Comparer deux Moteurs IA",
                "✨ Comparer deux Prompts / Personas",
                "⚡ Comparer deux Pipelines DAG",
            ]
        )
        config_bar.addWidget(self.mode_combo)

        # Agent Commun (affiché en mode Modèle vs Modèle)
        self.global_persona_widget = QWidget()
        gp_layout = QHBoxLayout(self.global_persona_widget)
        gp_layout.setContentsMargins(0, 0, 0, 0)
        gp_layout.setSpacing(6)
        lbl_gp = QLabel("Agent Commun :")
        lbl_gp.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
        self.persona_combo = StyledComboBox()
        gp_layout.addWidget(lbl_gp)
        gp_layout.addWidget(self.persona_combo)
        config_bar.addWidget(self.global_persona_widget)

        # Moteur Commun (affiché en mode Prompt vs Prompt et Pipeline vs Pipeline)
        self.global_engine_widget = QWidget()
        ge_layout = QHBoxLayout(self.global_engine_widget)
        ge_layout.setContentsMargins(0, 0, 0, 0)
        ge_layout.setSpacing(6)
        lbl_ge = QLabel("Moteur Commun :")
        lbl_ge.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
        self.global_engine_combo = StyledComboBox()
        ge_layout.addWidget(lbl_ge)
        ge_layout.addWidget(self.global_engine_combo)
        config_bar.addWidget(self.global_engine_widget)
        self.global_engine_widget.hide()

        # Modèle NoteType cible
        lbl_nt = QLabel("Modèle Cible :")
        lbl_nt.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
        config_bar.addWidget(lbl_nt)
        self.model_combo = StyledComboBox()
        config_bar.addWidget(self.model_combo)

        # Option de synchronisation de navigation
        self.chk_sync_nav = QCheckBox("Synchro A ↔ B")
        self.chk_sync_nav.setChecked(True)
        self.chk_sync_nav.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_sync_nav.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px; font-weight: 500;")
        config_bar.addWidget(self.chk_sync_nav)

        config_bar.addStretch()

        # Bouton Lancement A/B
        self.btn_run = PrimaryButton("Lancer le Test A/B")
        self.btn_run.setIcon(load_phosphor_icon("ph.play", color="white"))
        config_bar.addWidget(self.btn_run)

        ab_layout.addWidget(config_bar_widget)

        # Paramètres Avancés Globaux
        self.global_adv_widget, self.global_temp_slider, self.global_tok_slider = self._build_advanced_settings()
        self.global_adv_widget.hide()
        ab_layout.addWidget(self.global_adv_widget)

        # ── 2. SECTION TEXTE SOURCE ───────────────────────────────────────────
        source_box = QFrame()
        source_box.setObjectName("SourceBox")
        source_box.setFixedHeight(100)
        source_box.setStyleSheet(f"QFrame#SourceBox {{ background-color: {DesignTokens.BG_INPUT}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: {DesignTokens.RADIUS_MD}px; }}")
        source_layout = QVBoxLayout(source_box)
        source_layout.setContentsMargins(10, 6, 10, 6)
        source_layout.setSpacing(4)

        src_header = QHBoxLayout()
        lbl_src_title = QLabel("TEXTE SOURCE D'ENTRÉE :")
        lbl_src_title.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        src_header.addWidget(lbl_src_title)
        src_header.addStretch()

        self.lbl_src_chars = QLabel("0 caractères")
        self.lbl_src_chars.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-family: monospace;")
        src_header.addWidget(self.lbl_src_chars)
        source_layout.addLayout(src_header)

        self.source_text_edit = StyledTextEdit()
        self.source_text_edit.setPlaceholderText("Collez ici l'extrait de cours ou la consigne à tester dans le laboratoire A/B...")
        self.source_text_edit.setStyleSheet("border: none; background: transparent; font-size: 12px;")
        self.source_text_edit.textChanged.connect(lambda: self.lbl_src_chars.setText(f"{len(self.source_text_edit.toPlainText())} caractères"))
        source_layout.addWidget(self.source_text_edit, 1)

        ab_layout.addWidget(source_box)

        # ── 3. COMPARATIF CÔTE-À-CÔTE (BRANCHE A VS BRANCHE B) ─────────────────
        self.compare_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.compare_splitter.setStyleSheet(f"""
            QSplitter::handle {{
                background-color: {DesignTokens.BORDER_COLOR};
                width: 2px;
            }}
        """)
        ab_layout.addWidget(self.compare_splitter, 1)

        # ── PANNEAU A (Thème Violet/Indigo) ──
        self.panel_a = QFrame()
        self.panel_a.setObjectName("PanelA")
        self.panel_a.setStyleSheet(f"QFrame#PanelA {{ background-color: {DesignTokens.BG_INPUT}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: {DesignTokens.RADIUS_MD}px; }}")
        layout_a = QVBoxLayout(self.panel_a)
        layout_a.setContentsMargins(0, 0, 0, 0)
        layout_a.setSpacing(0)

        # En-tête A
        toolbar_a = QHBoxLayout()
        toolbar_a.setContentsMargins(10, 8, 10, 8)
        self.lbl_a = QLabel("Moteur A :")
        self.lbl_a.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
        self.engine_a_combo = StyledComboBox()
        self.persona_a_combo = StyledComboBox()
        self.persona_a_combo.hide()
        self.pipeline_a_combo = StyledComboBox()
        self.pipeline_a_combo.hide()

        toolbar_a.addWidget(self.lbl_a)
        toolbar_a.addWidget(self.engine_a_combo, 1)
        toolbar_a.addWidget(self.persona_a_combo, 1)
        toolbar_a.addWidget(self.pipeline_a_combo, 1)
        layout_a.addLayout(toolbar_a)

        # KPIs A
        self.kpi_a = BranchKpiWidget("BRANCHE A", color_hex="#8b5cf6")
        layout_a.addWidget(self.kpi_a)

        self.adv_widget_a, self.temp_slider_a, self.tok_slider_a = self._build_advanced_settings()
        layout_a.addWidget(self.adv_widget_a)

        # Sous-onglets A (Rendu Cartes / Tableau Champs / JSON Brut)
        self.subtabs_a = IdeTabBar()
        self.subtabs_a.add_tab("Rendu Cartes", "ph.eye")
        self.subtabs_a.add_tab("Tableau des Champs", "ph.table")
        self.subtabs_a.add_tab("JSON Brut", "ph.code")
        layout_a.addWidget(self.subtabs_a)

        # Navigation A
        nav_a = QHBoxLayout()
        nav_a.setContentsMargins(10, 4, 10, 4)
        self.btn_prev_a = IconButton("ph.caret-left", size=18)
        self.lbl_count_a = QLabel("0 / 0")
        self.lbl_count_a.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-family: {DesignTokens.FONT_CODE}; font-size: 11px; font-weight: bold;")
        self.btn_next_a = IconButton("ph.caret-right", size=18)

        self.btn_import_a = SecondaryButton("Importer dans la Forge")
        self.btn_import_a.setIcon(load_phosphor_icon("ph.arrow-down", color=DesignTokens.TEXT_PRIMARY))
        self.btn_import_a.clicked.connect(lambda: self._on_import_branch_to_forge("A"))

        nav_a.addWidget(self.btn_prev_a)
        nav_a.addStretch()
        nav_a.addWidget(self.lbl_count_a)
        nav_a.addStretch()
        nav_a.addWidget(self.btn_next_a)
        nav_a.addWidget(self.btn_import_a)
        layout_a.addLayout(nav_a)

        # Stack de visualisation A
        self.stack_a = QStackedWidget()
        self.preview_a = CardPreviewWidget(show_header=True)

        self.table_a = QTableWidget()
        self.table_a.setColumnCount(2)
        self.table_a.setHorizontalHeaderLabels(["Champ NoteType", "Valeur Générée"])
        self.table_a.horizontalHeader().setStretchLastSection(True)
        self.table_a.setStyleSheet(f"""
            QTableWidget {{
                background-color: {DesignTokens.BG_MAIN};
                color: {DesignTokens.TEXT_PRIMARY};
                border: none;
                gridline-color: {DesignTokens.BORDER_COLOR};
            }}
            QHeaderView::section {{
                background-color: {DesignTokens.BG_INPUT};
                color: {DesignTokens.TEXT_MUTED};
                font-weight: bold;
                border: 1px solid {DesignTokens.BORDER_COLOR};
                padding: 4px;
            }}
        """)

        self.json_edit_a = StyledTextEdit()
        self.json_edit_a.setReadOnly(True)
        self.json_edit_a.setStyleSheet(
            f"QPlainTextEdit {{ background-color: {DesignTokens.BG_PANEL}; color: {DesignTokens.TEXT_PRIMARY}; "
            f"font-family: '{DesignTokens.FONT_CODE}', monospace; font-size: 12px; border: none; padding: 10px; }}"
        )

        self.stack_a.addWidget(self.preview_a)
        self.stack_a.addWidget(self.table_a)
        self.stack_a.addWidget(self.json_edit_a)
        layout_a.addWidget(self.stack_a, 1)

        self.compare_splitter.addWidget(self.panel_a)

        # ── PANNEAU B (Thème Cyan/Émeraude) ──
        self.panel_b = QFrame()
        self.panel_b.setObjectName("PanelB")
        self.panel_b.setStyleSheet(f"QFrame#PanelB {{ background-color: {DesignTokens.BG_INPUT}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: {DesignTokens.RADIUS_MD}px; }}")
        layout_b = QVBoxLayout(self.panel_b)
        layout_b.setContentsMargins(0, 0, 0, 0)
        layout_b.setSpacing(0)

        # En-tête B
        toolbar_b = QHBoxLayout()
        toolbar_b.setContentsMargins(10, 8, 10, 8)
        self.lbl_b = QLabel("Moteur B :")
        self.lbl_b.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
        self.engine_b_combo = StyledComboBox()
        self.persona_b_combo = StyledComboBox()
        self.persona_b_combo.hide()
        self.pipeline_b_combo = StyledComboBox()
        self.pipeline_b_combo.hide()

        toolbar_b.addWidget(self.lbl_b)
        toolbar_b.addWidget(self.engine_b_combo, 1)
        toolbar_b.addWidget(self.persona_b_combo, 1)
        toolbar_b.addWidget(self.pipeline_b_combo, 1)
        layout_b.addLayout(toolbar_b)

        # KPIs B
        self.kpi_b = BranchKpiWidget("BRANCHE B", color_hex="#06b6d4")
        layout_b.addWidget(self.kpi_b)

        self.adv_widget_b, self.temp_slider_b, self.tok_slider_b = self._build_advanced_settings()
        layout_b.addWidget(self.adv_widget_b)

        # Sous-onglets B
        self.subtabs_b = IdeTabBar()
        self.subtabs_b.add_tab("Rendu Cartes", "ph.eye")
        self.subtabs_b.add_tab("Tableau des Champs", "ph.table")
        self.subtabs_b.add_tab("JSON Brut", "ph.code")
        layout_b.addWidget(self.subtabs_b)

        # Navigation B
        nav_b = QHBoxLayout()
        nav_b.setContentsMargins(10, 4, 10, 4)
        self.btn_prev_b = IconButton("ph.caret-left", size=18)
        self.lbl_count_b = QLabel("0 / 0")
        self.lbl_count_b.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-family: {DesignTokens.FONT_CODE}; font-size: 11px; font-weight: bold;")
        self.btn_next_b = IconButton("ph.caret-right", size=18)

        self.btn_import_b = SecondaryButton("Importer dans la Forge")
        self.btn_import_b.setIcon(load_phosphor_icon("ph.arrow-down", color=DesignTokens.TEXT_PRIMARY))
        self.btn_import_b.clicked.connect(lambda: self._on_import_branch_to_forge("B"))

        nav_b.addWidget(self.btn_prev_b)
        nav_b.addStretch()
        nav_b.addWidget(self.lbl_count_b)
        nav_b.addStretch()
        nav_b.addWidget(self.btn_next_b)
        nav_b.addWidget(self.btn_import_b)
        layout_b.addLayout(nav_b)

        # Stack de visualisation B
        self.stack_b = QStackedWidget()
        self.preview_b = CardPreviewWidget(show_header=True)

        self.table_b = QTableWidget()
        self.table_b.setColumnCount(2)
        self.table_b.setHorizontalHeaderLabels(["Champ NoteType", "Valeur Générée"])
        self.table_b.horizontalHeader().setStretchLastSection(True)
        self.table_b.setStyleSheet(f"""
            QTableWidget {{
                background-color: {DesignTokens.BG_MAIN};
                color: {DesignTokens.TEXT_PRIMARY};
                border: none;
                gridline-color: {DesignTokens.BORDER_COLOR};
            }}
            QHeaderView::section {{
                background-color: {DesignTokens.BG_INPUT};
                color: {DesignTokens.TEXT_MUTED};
                font-weight: bold;
                border: 1px solid {DesignTokens.BORDER_COLOR};
                padding: 4px;
            }}
        """)

        self.json_edit_b = StyledTextEdit()
        self.json_edit_b.setReadOnly(True)
        self.json_edit_b.setStyleSheet(
            f"QPlainTextEdit {{ background-color: {DesignTokens.BG_PANEL}; color: {DesignTokens.TEXT_PRIMARY}; "
            f"font-family: '{DesignTokens.FONT_CODE}', monospace; font-size: 12px; border: none; padding: 10px; }}"
        )

        self.stack_b.addWidget(self.preview_b)
        self.stack_b.addWidget(self.table_b)
        self.stack_b.addWidget(self.json_edit_b)
        layout_b.addWidget(self.stack_b, 1)

        self.compare_splitter.addWidget(self.panel_b)
        self.compare_splitter.setSizes([500, 500])

        self.ab_panel.add_tab("Laboratoire A/B", ab_content, "ph.scales", closable=False)
        main_layout.addWidget(self.ab_panel)

    def _connect_signals(self) -> None:
        self.btn_run.clicked.connect(self._on_run_ab_test)

        self.subtabs_a.tab_changed.connect(self.stack_a.setCurrentIndex)
        self.subtabs_b.tab_changed.connect(self.stack_b.setCurrentIndex)

        self.btn_prev_a.clicked.connect(self._prev_a)
        self.btn_next_a.clicked.connect(self._next_a)

        self.btn_prev_b.clicked.connect(self._prev_b)
        self.btn_next_b.clicked.connect(self._next_b)

        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)

    @Slot()
    def _on_mode_changed(self) -> None:
        idx = self.mode_combo.currentIndex()
        if idx == 0:
            # Mode "Comparer deux Moteurs IA"
            self.global_persona_widget.show()
            self.global_engine_widget.hide()
            self.global_adv_widget.hide()

            self.lbl_a.setText("Moteur A :")
            self.engine_a_combo.show()
            self.persona_a_combo.hide()
            self.pipeline_a_combo.hide()
            self.adv_widget_a.show()

            self.lbl_b.setText("Moteur B :")
            self.engine_b_combo.show()
            self.persona_b_combo.hide()
            self.pipeline_b_combo.hide()
            self.adv_widget_b.show()
        elif idx == 1:
            # Mode "Comparer deux Prompts / Personas"
            self.global_persona_widget.hide()
            self.global_engine_widget.show()
            self.global_adv_widget.show()

            self.lbl_a.setText("Prompt A :")
            self.engine_a_combo.hide()
            self.persona_a_combo.show()
            self.pipeline_a_combo.hide()
            self.adv_widget_a.hide()

            self.lbl_b.setText("Prompt B :")
            self.engine_b_combo.hide()
            self.persona_b_combo.show()
            self.pipeline_b_combo.hide()
            self.adv_widget_b.hide()
        else:
            # Mode "Comparer deux Pipelines DAG"
            self.global_persona_widget.hide()
            self.global_engine_widget.show()
            self.global_adv_widget.show()

            self.lbl_a.setText("Pipeline A :")
            self.engine_a_combo.hide()
            self.persona_a_combo.hide()
            self.pipeline_a_combo.show()
            self.adv_widget_a.hide()

            self.lbl_b.setText("Pipeline B :")
            self.engine_b_combo.hide()
            self.persona_b_combo.hide()
            self.pipeline_b_combo.show()
            self.adv_widget_b.hide()

    def refresh_data(self) -> None:
        """Recharge les moteurs, agents, pipelines et modèles depuis Peewee DB."""
        try:
            self.engine_a_combo.blockSignals(True)
            self.engine_b_combo.blockSignals(True)
            self.global_engine_combo.blockSignals(True)
            self.engine_a_combo.clear()
            self.engine_b_combo.clear()
            self.global_engine_combo.clear()

            engines = list(LLMConfigModel.select())
            for eg in engines:
                self.engine_a_combo.addItem(eg.display_name or eg.provider, userData=eg)
                self.engine_b_combo.addItem(eg.display_name or eg.provider, userData=eg)
                self.global_engine_combo.addItem(eg.display_name or eg.provider, userData=eg)
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

        except Exception as e:
            logger.warning("Erreur refresh_data ab_tests_view: %s", e)

    def is_dirty(self) -> bool:
        return False

    def _insert_mock_initial_data(self) -> None:
        """Données initiales de démonstration."""
        self.source_text_edit.setPlainText("L'insuffisance cardiaque droite est caractérisée par l'incapacité du ventricule droit à assurer un débit sanguin suffisant.")

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

            # Table A
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

            # Table B
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
            # Moteur A vs Moteur B
            engine_a = self.engine_a_combo.currentData()
            engine_b = self.engine_b_combo.currentData()
            pipe_id_a = None
            pipe_id_b = None
            common_persona = self.persona_combo.currentData()
            if common_persona:
                steps_a = [PipelineStepModel(persona=common_persona, step_type="LLM_PROMPT", step_order=1)]
                steps_b = [PipelineStepModel(persona=common_persona, step_type="LLM_PROMPT", step_order=1)]

        elif mode_idx == 1:
            # Prompt A vs Prompt B
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
            # Pipeline A vs Pipeline B
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

        # Initialisation des états partagés
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

    def _extract_cards_from_state(self, state: PipelineRunState) -> List[Dict[str, Any]]:
        raw_cards = state.get_variable("generated_cards") or state.get_variable("map_reduce_results") or state.get_variable("last_output") or []
        if isinstance(raw_cards, list):
            return [c for c in raw_cards if isinstance(c, dict)]
        elif isinstance(raw_cards, dict) and "cards" in raw_cards and isinstance(raw_cards["cards"], list):
            return [c for c in raw_cards["cards"] if isinstance(c, dict)]
        return []

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

    def _check_test_complete(self) -> None:
        if self._completed_a and self._completed_b:
            self.btn_run.setEnabled(True)
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

        try:
            # Récupérer ou créer un Deck par défaut
            deck = DeckModel.get_or_none(DeckModel.name == "Défaut")
            if not deck:
                deck = DeckModel.create(name="Défaut")

            imported_count = 0
            with db.atomic():
                for card_dict in cards:
                    note = NoteModel.create(
                        guid=uuid.uuid4().hex,
                        note_type=selected_nt,
                        tags="ab_test",
                    )
                    note.add_version(card_dict, source="ai_ab_test")
                    CardModel.create(note=note, deck=deck, template_index=0)
                    imported_count += 1

            show_toast(self, f"{imported_count} cartes de la Branche {branch} importées avec succès dans la Forge !")
        except Exception as e:
            logger.exception("Erreur lors de l'import des cartes A/B dans la Forge")
            show_toast(self, f"Erreur lors de l'import : {e}", is_error=True)

    def refresh_theme(self, profile: Any) -> None:
        """Rafraîchit à chaud les composants et aperçus de cartes A/B lors d'un changement de thème."""
        if hasattr(self, "preview_a") and hasattr(self.preview_a, "refresh_theme"):
            self.preview_a.refresh_theme(profile)
        if hasattr(self, "preview_b") and hasattr(self.preview_b, "refresh_theme"):
            self.preview_b.refresh_theme(profile)
        if hasattr(self, "tab_bar_a"):
            self.tab_bar_a.update()
        if hasattr(self, "tab_bar_b"):
            self.tab_bar_b.update()


ABTestsTab = ABTestsView

"""
Vue Laboratoire A/B (Tests A/B) — 100% Conforme à la Maquette concept_ide.
- Panneau de configuration supérieure (Mode de comparaison, Agent/Prompt, Modèle Anki, Recto/Verso).
- Zone de saisie du Texte Source à tester.
- Comparaison symétrique côte-à-côte (Moteur A vs Moteur B) avec sélecteurs de modèles IA, sous-onglets Rendu Cartes / JSON Brut, et navigation 1/N.
- Exécution asynchrone via CreationWorker et rendu réactif via CardPreviewWidget.
"""

import json
import logging
from typing import Any, Optional

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
    QSlider,
)

from ankiforge.database.models import PersonaModel, LLMConfigModel, NoteTypeModel
from ankiforge.services.workers.creation_worker import CreationTaskPayload, CreationWorker
from ankiforge.ui.components import (
    IconButton,
    IdePanel,
    PrimaryButton,
    StyledComboBox,
    StyledTextEdit,
)
from ankiforge.ui.components.tabs import IdeTabBar
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.card_preview_widget import CardPreviewWidget
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class ABTestsView(QWidget):
    """
    Vue Laboratoire A/B — 100% Conforme à la Maquette concept_ide.
    """

    def __init__(self, ai_manager: Optional[Any] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.ai_manager = ai_manager

        self.cards_a: list[dict[str, Any]] = []
        self.index_a: int = 0

        self.cards_b: list[dict[str, Any]] = []
        self.index_b: int = 0

        self.worker_a: Optional[CreationWorker] = None
        self.worker_b: Optional[CreationWorker] = None

        self._setup_ui()
        self._connect_signals()
        self.refresh_data()
        self._insert_mock_initial_data()

    def _build_advanced_settings(self) -> tuple[QWidget, QSlider, QSlider]:
        adv_widget = QWidget()
        adv_layout = QHBoxLayout(adv_widget)
        adv_layout.setContentsMargins(12, 4, 12, 4)
        adv_layout.setSpacing(16)

        lbl_temp = QLabel("Température :")
        lbl_temp.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")

        temp_slider = QSlider(Qt.Orientation.Horizontal)
        temp_slider.setRange(0, 200)
        temp_slider.setValue(70)
        temp_slider.setFixedWidth(120)

        slider_style = f"""
            QSlider::groove:horizontal {{
                border: 1px solid #333;
                height: 4px;
                background: #1e1e1e;
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
            QSlider::add-page:horizontal {{
                background: #1e1e1e;
            }}
            QSlider::sub-page:horizontal {{
                background: {DesignTokens.ACCENT_PRIMARY};
            }}
        """
        temp_slider.setStyleSheet(slider_style)

        lbl_temp_val = QLabel("0.70")
        lbl_temp_val.setStyleSheet(f"color: {DesignTokens.ACCENT_PRIMARY}; font-size: 11px; font-weight: bold;")
        temp_slider.valueChanged.connect(lambda v, lbl=lbl_temp_val: lbl.setText(f"{v/100:.2f}"))

        adv_layout.addWidget(lbl_temp)
        adv_layout.addWidget(temp_slider)
        adv_layout.addWidget(lbl_temp_val)

        lbl_tok = QLabel("Max Tokens :")
        lbl_tok.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")

        tok_slider = QSlider(Qt.Orientation.Horizontal)
        tok_slider.setRange(256, 8192)
        tok_slider.setValue(4096)
        tok_slider.setFixedWidth(120)
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

        # Bouton Lancer déplacé dans la barre de configuration
        self.btn_run = PrimaryButton("Lancer")
        self.btn_run.setIcon(load_phosphor_icon("ph.play", color="white"))

        ab_content = QWidget()
        ab_layout = QVBoxLayout(ab_content)
        ab_layout.setContentsMargins(12, 12, 12, 12)
        ab_layout.setSpacing(12)

        # Toolbar de configuration globale (Mode, Prompt, Modèle, Voir Recto/Verso)
        config_bar_widget = QWidget()
        config_bar_widget.setObjectName("ConfigBarWidget")
        config_bar_widget.setStyleSheet(
            f"QWidget#ConfigBarWidget {{ background-color: {DesignTokens.BG_PANEL}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: {DesignTokens.RADIUS_MD}px; }}"
        )
        config_bar = QHBoxLayout(config_bar_widget)
        config_bar.setContentsMargins(12, 8, 12, 8)
        config_bar.setSpacing(10)

        def add_cfg(label_text: str, widget: QWidget) -> None:
            grp = QHBoxLayout()
            grp.setSpacing(6)
            lbl = QLabel(label_text)
            lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
            grp.addWidget(lbl)
            grp.addWidget(widget)
            config_bar.addLayout(grp)

        self.mode_combo = StyledComboBox()
        self.mode_combo.addItems(["Comparer deux Moteurs IA", "Comparer deux Prompts"])
        add_cfg("Mode :", self.mode_combo)

        # Global Persona (used when comparing engines)
        self.global_persona_widget = QWidget()
        gp_layout = QHBoxLayout(self.global_persona_widget)
        gp_layout.setContentsMargins(0, 0, 0, 0)
        gp_layout.setSpacing(6)
        lbl_gp = QLabel("Prompt/Pipe :")
        lbl_gp.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
        self.persona_combo = StyledComboBox()
        gp_layout.addWidget(lbl_gp)
        gp_layout.addWidget(self.persona_combo)
        config_bar.addWidget(self.global_persona_widget)

        # Global Engine (used when comparing prompts)
        self.global_engine_widget = QWidget()
        ge_layout = QHBoxLayout(self.global_engine_widget)
        ge_layout.setContentsMargins(0, 0, 0, 0)
        ge_layout.setSpacing(6)
        lbl_ge = QLabel("Moteur :")
        lbl_ge.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
        self.global_engine_combo = StyledComboBox()
        ge_layout.addWidget(lbl_ge)
        ge_layout.addWidget(self.global_engine_combo)
        config_bar.addWidget(self.global_engine_widget)
        self.global_engine_widget.hide()

        self.model_combo = StyledComboBox()
        add_cfg("Modèle :", self.model_combo)

        config_bar.addStretch()
        config_bar.addWidget(self.btn_run)

        ab_layout.addWidget(config_bar_widget)

        # Paramètres Avancés Globaux (visibles en mode Comparer deux Prompts)
        self.global_adv_widget, self.global_temp_slider, self.global_tok_slider = self._build_advanced_settings()
        self.global_adv_widget.hide()
        ab_layout.addWidget(self.global_adv_widget)

        # Section Texte Source
        source_box = QFrame()
        source_box.setObjectName("SourceBox")
        source_box.setFixedHeight(120)
        source_box.setStyleSheet(f"QFrame#SourceBox {{ background-color: #1a1d24; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: {DesignTokens.RADIUS_MD}px; }}")
        source_layout = QVBoxLayout(source_box)
        source_layout.setContentsMargins(12, 8, 12, 8)
        source_layout.setSpacing(4)

        lbl_src_title = QLabel("TEXTE SOURCE :")
        lbl_src_title.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        source_layout.addWidget(lbl_src_title)

        self.source_text_edit = StyledTextEdit()
        self.source_text_edit.setPlaceholderText("Collez ici l'extrait de cours à tester dans le laboratoire A/B...")
        self.source_text_edit.setStyleSheet("border: none; background: transparent; font-size: 13px;")
        source_layout.addWidget(self.source_text_edit, 1)

        ab_layout.addWidget(source_box)

        # Comparaison côte-à-côte (Splitter Horizontal Moteur A / Moteur B)
        self.compare_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.compare_splitter.setStyleSheet(f"""
            QSplitter::handle {{
                background-color: {DesignTokens.BORDER_COLOR};
                width: 2px;
            }}
        """)
        ab_layout.addWidget(self.compare_splitter, 1)

        # --- PANNEAU A (Moteur A) ---
        self.panel_a = QFrame()
        self.panel_a.setObjectName("PanelA")
        self.panel_a.setStyleSheet(f"QFrame#PanelA {{ background-color: #1a1d24; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: {DesignTokens.RADIUS_MD}px; }}")
        layout_a = QVBoxLayout(self.panel_a)
        layout_a.setContentsMargins(0, 0, 0, 0)
        layout_a.setSpacing(0)

        # Header Panel A
        toolbar_a = QHBoxLayout()
        toolbar_a.setContentsMargins(10, 8, 10, 8)
        self.lbl_a = QLabel("Moteur A :")
        self.lbl_a.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
        self.engine_a_combo = StyledComboBox()
        self.persona_a_combo = StyledComboBox()
        self.persona_a_combo.hide()
        toolbar_a.addWidget(self.lbl_a)
        toolbar_a.addWidget(self.engine_a_combo, 1)
        toolbar_a.addWidget(self.persona_a_combo, 1)
        layout_a.addLayout(toolbar_a)

        self.adv_widget_a, self.temp_slider_a, self.tok_slider_a = self._build_advanced_settings()
        layout_a.addWidget(self.adv_widget_a)

        # Sub-tabs A (Onglets stylisés Maquette concept_ide)
        self.subtabs_a = IdeTabBar()
        self.subtabs_a.add_tab("Rendu Cartes", "👁️")
        self.subtabs_a.add_tab("JSON Brut", "💻")
        layout_a.addWidget(self.subtabs_a)

        # Navigation A
        nav_a = QHBoxLayout()
        nav_a.setContentsMargins(10, 4, 10, 4)
        self.btn_prev_a = IconButton("ph.caret-left", size=18)
        self.lbl_count_a = QLabel("0 / 0")
        self.lbl_count_a.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-family: {DesignTokens.FONT_CODE}; font-size: 11px; font-weight: bold;")
        self.btn_next_a = IconButton("ph.caret-right", size=18)

        nav_a.addWidget(self.btn_prev_a)
        nav_a.addStretch()
        nav_a.addWidget(self.lbl_count_a)
        nav_a.addStretch()
        nav_a.addWidget(self.btn_next_a)
        layout_a.addLayout(nav_a)

        # Content Stack A (Page 0: CardPreviewWidget, Page 1: Raw JSON)
        self.stack_a = QStackedWidget()
        self.preview_a = CardPreviewWidget(show_header=True)
        self.json_edit_a = StyledTextEdit()
        self.json_edit_a.setReadOnly(True)
        self.json_edit_a.setStyleSheet("QPlainTextEdit { background-color: #090a0f; color: #a5b4fc; font-family: Menlo; border: none; padding: 10px; }")

        self.stack_a.addWidget(self.preview_a)
        self.stack_a.addWidget(self.json_edit_a)
        layout_a.addWidget(self.stack_a, 1)

        self.compare_splitter.addWidget(self.panel_a)

        # --- PANNEAU B (Moteur B) ---
        self.panel_b = QFrame()
        self.panel_b.setObjectName("PanelB")
        self.panel_b.setStyleSheet(f"QFrame#PanelB {{ background-color: #1a1d24; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: {DesignTokens.RADIUS_MD}px; }}")
        layout_b = QVBoxLayout(self.panel_b)
        layout_b.setContentsMargins(0, 0, 0, 0)
        layout_b.setSpacing(0)

        # Header Panel B
        toolbar_b = QHBoxLayout()
        toolbar_b.setContentsMargins(10, 8, 10, 8)
        self.lbl_b = QLabel("Moteur B :")
        self.lbl_b.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
        self.engine_b_combo = StyledComboBox()
        self.persona_b_combo = StyledComboBox()
        self.persona_b_combo.hide()
        toolbar_b.addWidget(self.lbl_b)
        toolbar_b.addWidget(self.engine_b_combo, 1)
        toolbar_b.addWidget(self.persona_b_combo, 1)
        layout_b.addLayout(toolbar_b)

        self.adv_widget_b, self.temp_slider_b, self.tok_slider_b = self._build_advanced_settings()
        layout_b.addWidget(self.adv_widget_b)

        # Sub-tabs B (Onglets stylisés Maquette concept_ide)
        self.subtabs_b = IdeTabBar()
        self.subtabs_b.add_tab("Rendu Cartes", "👁️")
        self.subtabs_b.add_tab("JSON Brut", "💻")
        layout_b.addWidget(self.subtabs_b)

        # Navigation B
        nav_b = QHBoxLayout()
        nav_b.setContentsMargins(10, 4, 10, 4)
        self.btn_prev_b = IconButton("ph.caret-left", size=18)
        self.lbl_count_b = QLabel("0 / 0")
        self.lbl_count_b.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-family: {DesignTokens.FONT_CODE}; font-size: 11px; font-weight: bold;")
        self.btn_next_b = IconButton("ph.caret-right", size=18)

        nav_b.addWidget(self.btn_prev_b)
        nav_b.addStretch()
        nav_b.addWidget(self.lbl_count_b)
        nav_b.addStretch()
        nav_b.addWidget(self.btn_next_b)
        layout_b.addLayout(nav_b)

        # Content Stack B (Page 0: CardPreviewWidget, Page 1: Raw JSON)
        self.stack_b = QStackedWidget()
        self.preview_b = CardPreviewWidget(show_header=True)
        self.json_edit_b = StyledTextEdit()
        self.json_edit_b.setReadOnly(True)
        self.json_edit_b.setStyleSheet("QPlainTextEdit { background-color: #090a0f; color: #a5b4fc; font-family: Menlo; border: none; padding: 10px; }")

        self.stack_b.addWidget(self.preview_b)
        self.stack_b.addWidget(self.json_edit_b)
        layout_b.addWidget(self.stack_b, 1)

        self.compare_splitter.addWidget(self.panel_b)

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
        if self.mode_combo.currentIndex() == 0:
            # Mode "Comparer deux Moteurs IA"
            self.global_persona_widget.show()
            self.global_engine_widget.hide()
            self.global_adv_widget.hide()

            self.lbl_a.setText("Moteur A :")
            self.engine_a_combo.show()
            self.persona_a_combo.hide()
            self.adv_widget_a.show()

            self.lbl_b.setText("Moteur B :")
            self.engine_b_combo.show()
            self.persona_b_combo.hide()
            self.adv_widget_b.show()
        else:
            # Mode "Comparer deux Prompts"
            self.global_persona_widget.hide()
            self.global_engine_widget.show()
            self.global_adv_widget.show()

            self.lbl_a.setText("Prompt A :")
            self.engine_a_combo.hide()
            self.persona_a_combo.show()
            self.adv_widget_a.hide()

            self.lbl_b.setText("Prompt B :")
            self.engine_b_combo.hide()
            self.persona_b_combo.show()
            self.adv_widget_b.hide()

    def refresh_data(self) -> None:
        """Recharge les moteurs, agents et modèles depuis Peewee DB."""
        try:
            self.engine_a_combo.blockSignals(True)
            self.engine_b_combo.blockSignals(True)
            self.engine_a_combo.clear()
            self.engine_b_combo.clear()

            engines = list(LLMConfigModel.select())
            if engines:
                for eg in engines:
                    self.engine_a_combo.addItem(eg.display_name, userData=eg)
                    self.engine_b_combo.addItem(eg.display_name, userData=eg)
                    self.global_engine_combo.addItem(eg.display_name, userData=eg)
                if len(engines) > 1:
                    self.engine_b_combo.setCurrentIndex(1)
            else:
                self.engine_a_combo.addItem("Claude 3.5 Sonnet")
                self.engine_b_combo.addItem("GPT-4o")
                self.global_engine_combo.addItem("Claude 3.5 Sonnet")

            self.engine_a_combo.blockSignals(False)
            self.engine_b_combo.blockSignals(False)
            self.global_engine_combo.blockSignals(False)

            self.persona_combo.blockSignals(True)
            self.persona_a_combo.blockSignals(True)
            self.persona_b_combo.blockSignals(True)
            self.persona_combo.clear()
            self.persona_a_combo.clear()
            self.persona_b_combo.clear()
            for ag in PersonaModel.select():
                self.persona_combo.addItem(ag.name, userData=ag)
                self.persona_a_combo.addItem(ag.name, userData=ag)
                self.persona_b_combo.addItem(ag.name, userData=ag)
            self.persona_combo.blockSignals(False)
            self.persona_a_combo.blockSignals(False)
            self.persona_b_combo.blockSignals(False)

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
        """Données de démonstration initiales conformes à la maquette."""
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
                pass

        f_front = fields[0] if len(fields) > 0 else "Front"
        f_back = fields[1] if len(fields) > 1 else "Back"

        # Side A
        if self.cards_a:
            self.lbl_count_a.setText(f"{self.index_a + 1} / {len(self.cards_a)}")
            current_card_a = self.cards_a[self.index_a]
            self.json_edit_a.setPlainText(json.dumps(current_card_a, ensure_ascii=False, indent=2))

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

        # Side B
        if self.cards_b:
            self.lbl_count_b.setText(f"{self.index_b + 1} / {len(self.cards_b)}")
            current_card_b = self.cards_b[self.index_b]
            self.json_edit_b.setPlainText(json.dumps(current_card_b, ensure_ascii=False, indent=2))

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

    @Slot()
    def _prev_a(self) -> None:
        if self.cards_a and self.index_a > 0:
            self.index_a -= 1
            self._update_views()

    @Slot()
    def _next_a(self) -> None:
        if self.cards_a and self.index_a < len(self.cards_a) - 1:
            self.index_a += 1
            self._update_views()

    @Slot()
    def _prev_b(self) -> None:
        if self.cards_b and self.index_b > 0:
            self.index_b -= 1
            self._update_views()

    @Slot()
    def _next_b(self) -> None:
        if self.cards_b and self.index_b < len(self.cards_b) - 1:
            self.index_b += 1
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

        is_engine_mode = self.mode_combo.currentIndex() == 0

        engine_a = self.engine_a_combo.currentData() if is_engine_mode else self.global_engine_combo.currentData()
        engine_b = self.engine_b_combo.currentData() if is_engine_mode else self.global_engine_combo.currentData()

        persona_a = self.persona_combo.currentData() if is_engine_mode else self.persona_a_combo.currentData()
        persona_b = self.persona_combo.currentData() if is_engine_mode else self.persona_b_combo.currentData()

        if not persona_a or not persona_b:
            show_toast(self, "Il manque un prompt/agent configuré !", is_error=True)
            return

        show_toast(self, "Lancement du test A/B en parallèle...")
        self.btn_run.setEnabled(False)

        # Application des paramètres avancés (température et max_tokens)
        if is_engine_mode:
            temp_a = self.temp_slider_a.value() / 100.0
            tok_a = self.tok_slider_a.value()
            temp_b = self.temp_slider_b.value() / 100.0
            tok_b = self.tok_slider_b.value()
        else:
            temp_a = temp_b = self.global_temp_slider.value() / 100.0
            tok_a = tok_b = self.global_tok_slider.value()

        provider_a = None
        provider_b = None

        if self.ai_manager:
            if engine_a and hasattr(self.ai_manager, "create_provider_from_config"):
                try:
                    engine_a.temperature = temp_a
                    engine_a.context_limit = tok_a
                    provider_a = self.ai_manager.create_provider_from_config(engine_a)
                except Exception:
                    pass  # nosec B110
            if engine_b and hasattr(self.ai_manager, "create_provider_from_config"):
                try:
                    engine_b.temperature = temp_b
                    engine_b.context_limit = tok_b
                    provider_b = self.ai_manager.create_provider_from_config(engine_b)
                except Exception:
                    pass  # nosec B110

        # Construct pipeline steps from Personas
        steps_a = [{"name": persona_a.name, "system_prompt": persona_a.system_prompt, "output_format": getattr(persona_a, "output_format", "json")}]

        steps_b = [{"name": persona_b.name, "system_prompt": persona_b.system_prompt, "output_format": getattr(persona_b, "output_format", "json")}]

        payload_a = CreationTaskPayload(
            text_source=text_source,
            note_type_id=nt_id,
            note_type_fields_schema=json.dumps(nt_schema, ensure_ascii=False),
            pipeline_id=1,
            pipeline_name="AB_Test_A",
            pipeline_steps=steps_a,
            use_vision=False,
        )

        payload_b = CreationTaskPayload(
            text_source=text_source,
            note_type_id=nt_id,
            note_type_fields_schema=json.dumps(nt_schema, ensure_ascii=False),
            pipeline_id=1,
            pipeline_name="AB_Test_B",
            pipeline_steps=steps_b,
            use_vision=False,
        )

        self.worker_a = CreationWorker(ai_provider=provider_a, payload=payload_a)
        self.worker_a.finished.connect(self._on_finished_a)
        self.worker_a.error.connect(lambda msg: show_toast(self, f"Erreur Moteur A: {msg}", is_error=True))

        self.worker_b = CreationWorker(ai_provider=provider_b, payload=payload_b)
        self.worker_b.finished.connect(self._on_finished_b)
        self.worker_b.error.connect(lambda msg: show_toast(self, f"Erreur Moteur B: {msg}", is_error=True))

        self.worker_a.start()
        self.worker_b.start()

    @Slot(list)
    def _on_finished_a(self, cards: list[dict[str, Any]]) -> None:
        self.cards_a = cards
        self.index_a = 0
        self._check_test_complete()

    @Slot(list)
    def _on_finished_b(self, cards: list[dict[str, Any]]) -> None:
        self.cards_b = cards
        self.index_b = 0
        self._check_test_complete()

    def _check_test_complete(self) -> None:
        if (not self.worker_a or not self.worker_a.isRunning()) and (not self.worker_b or not self.worker_b.isRunning()):
            self.btn_run.setEnabled(True)
            self._update_views()
            show_toast(self, "Test A/B terminé avec succès !")


ABTestsTab = ABTestsView

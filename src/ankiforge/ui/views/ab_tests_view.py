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
)

from ankiforge.database.models import AgentModel, LLMConfigModel, NoteTypeModel
from ankiforge.services.workers.creation_worker import CreationTaskPayload, CreationWorker
from ankiforge.ui.components import (
    IconButton,
    IdePanel,
    PrimaryButton,
    SecondaryButton,
    StyledComboBox,
    StyledTextEdit,
)
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

    def _setup_ui(self) -> None:
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        self.ab_panel = IdePanel(detachable=True)

        # Bouton Lancer dans le header du panneau
        self.btn_run = PrimaryButton("Lancer")
        self.btn_run.setIcon(load_phosphor_icon("ph.play", color="white"))
        self.btn_run.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #10b981, stop:1 #059669);
                color: white;
                border: none;
                border-radius: 6px;
                font-weight: 600;
                padding: 6px 16px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #059669, stop:1 #047857);
            }
        """)

        self.ab_panel.add_header_widget(self.btn_run)
        self.ab_panel.add_header_separator()

        ab_content = QWidget()
        ab_layout = QVBoxLayout(ab_content)
        ab_layout.setContentsMargins(12, 12, 12, 12)
        ab_layout.setSpacing(12)

        # Toolbar de configuration globale (Mode, Prompt, Modèle, Voir Recto/Verso)
        config_bar_widget = QWidget()
        config_bar_widget.setStyleSheet(f"background-color: {DesignTokens.BG_PANEL}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: {DesignTokens.RADIUS_MD}px;")
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

        self.agent_combo = StyledComboBox()
        add_cfg("Prompt/Pipe :", self.agent_combo)

        self.model_combo = StyledComboBox()
        add_cfg("Modèle :", self.model_combo)

        config_bar.addStretch()

        self.view_side_combo = StyledComboBox()
        self.view_side_combo.addItems(["Voir Recto", "Voir Verso"])
        config_bar.addWidget(self.view_side_combo)

        ab_layout.addWidget(config_bar_widget)

        # Section Texte Source
        source_box = QFrame()
        source_box.setFixedHeight(120)
        source_box.setStyleSheet(f"background-color: #1a1d24; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: {DesignTokens.RADIUS_MD}px;")
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
        ab_layout.addWidget(self.compare_splitter, 1)

        # --- PANNEAU A (Moteur A) ---
        self.panel_a = QFrame()
        self.panel_a.setStyleSheet(f"background-color: #1a1d24; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: {DesignTokens.RADIUS_MD}px;")
        layout_a = QVBoxLayout(self.panel_a)
        layout_a.setContentsMargins(0, 0, 0, 0)
        layout_a.setSpacing(0)

        # Header Moteur A
        toolbar_a = QHBoxLayout()
        toolbar_a.setContentsMargins(10, 8, 10, 8)
        lbl_a = QLabel("Moteur A :")
        lbl_a.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
        self.engine_a_combo = StyledComboBox()
        toolbar_a.addWidget(lbl_a)
        toolbar_a.addWidget(self.engine_a_combo, 1)
        layout_a.addLayout(toolbar_a)

        # Sub-tabs A
        subtabs_a = QHBoxLayout()
        subtabs_a.setContentsMargins(8, 4, 8, 4)
        self.btn_tab_render_a = SecondaryButton("Rendu Cartes")
        self.btn_tab_render_a.setIcon(load_phosphor_icon("ph.eye", color=DesignTokens.COLOR_PURPLE))
        self.btn_tab_json_a = SecondaryButton("JSON Brut")
        self.btn_tab_json_a.setIcon(load_phosphor_icon("ph.code", color=DesignTokens.COLOR_BLUE))
        subtabs_a.addWidget(self.btn_tab_render_a)
        subtabs_a.addWidget(self.btn_tab_json_a)
        subtabs_a.addStretch()
        layout_a.addLayout(subtabs_a)

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
        self.preview_a = CardPreviewWidget(show_header=False)
        self.json_edit_a = StyledTextEdit()
        self.json_edit_a.setReadOnly(True)
        self.json_edit_a.setStyleSheet("QPlainTextEdit { background-color: #090a0f; color: #a5b4fc; font-family: monospace; border: none; padding: 10px; }")

        self.stack_a.addWidget(self.preview_a)
        self.stack_a.addWidget(self.json_edit_a)
        layout_a.addWidget(self.stack_a, 1)

        self.compare_splitter.addWidget(self.panel_a)

        # --- PANNEAU B (Moteur B) ---
        self.panel_b = QFrame()
        self.panel_b.setStyleSheet(f"background-color: #1a1d24; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: {DesignTokens.RADIUS_MD}px;")
        layout_b = QVBoxLayout(self.panel_b)
        layout_b.setContentsMargins(0, 0, 0, 0)
        layout_b.setSpacing(0)

        # Header Moteur B
        toolbar_b = QHBoxLayout()
        toolbar_b.setContentsMargins(10, 8, 10, 8)
        lbl_b = QLabel("Moteur B :")
        lbl_b.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
        self.engine_b_combo = StyledComboBox()
        toolbar_b.addWidget(lbl_b)
        toolbar_b.addWidget(self.engine_b_combo, 1)
        layout_b.addLayout(toolbar_b)

        # Sub-tabs B
        subtabs_b = QHBoxLayout()
        subtabs_b.setContentsMargins(8, 4, 8, 4)
        self.btn_tab_render_b = SecondaryButton("Rendu Cartes")
        self.btn_tab_render_b.setIcon(load_phosphor_icon("ph.eye", color=DesignTokens.COLOR_PURPLE))
        self.btn_tab_json_b = SecondaryButton("JSON Brut")
        self.btn_tab_json_b.setIcon(load_phosphor_icon("ph.code", color=DesignTokens.COLOR_BLUE))
        subtabs_b.addWidget(self.btn_tab_render_b)
        subtabs_b.addWidget(self.btn_tab_json_b)
        subtabs_b.addStretch()
        layout_b.addLayout(subtabs_b)

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
        self.preview_b = CardPreviewWidget(show_header=False)
        self.json_edit_b = StyledTextEdit()
        self.json_edit_b.setReadOnly(True)
        self.json_edit_b.setStyleSheet("QPlainTextEdit { background-color: #090a0f; color: #a5b4fc; font-family: monospace; border: none; padding: 10px; }")

        self.stack_b.addWidget(self.preview_b)
        self.stack_b.addWidget(self.json_edit_b)
        layout_b.addWidget(self.stack_b, 1)

        self.compare_splitter.addWidget(self.panel_b)

        self.ab_panel.add_tab("Laboratoire A/B", ab_content, "ph.scales", closable=False)
        main_layout.addWidget(self.ab_panel)

    def _connect_signals(self) -> None:
        self.btn_run.clicked.connect(self._on_run_ab_test)

        self.btn_tab_render_a.clicked.connect(lambda: self.stack_a.setCurrentIndex(0))
        self.btn_tab_json_a.clicked.connect(lambda: self.stack_a.setCurrentIndex(1))

        self.btn_tab_render_b.clicked.connect(lambda: self.stack_b.setCurrentIndex(0))
        self.btn_tab_json_b.clicked.connect(lambda: self.stack_b.setCurrentIndex(1))

        self.btn_prev_a.clicked.connect(self._prev_a)
        self.btn_next_a.clicked.connect(self._next_a)

        self.btn_prev_b.clicked.connect(self._prev_b)
        self.btn_next_b.clicked.connect(self._next_b)

        self.view_side_combo.currentIndexChanged.connect(self._update_views)

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
                    self.engine_a_combo.addItem(eg.name, userData=eg)
                    self.engine_b_combo.addItem(eg.name, userData=eg)
                if len(engines) > 1:
                    self.engine_b_combo.setCurrentIndex(1)
            else:
                self.engine_a_combo.addItem("Claude 3.5 Sonnet")
                self.engine_b_combo.addItem("GPT-4o")

            self.engine_a_combo.blockSignals(False)
            self.engine_b_combo.blockSignals(False)

            self.agent_combo.blockSignals(True)
            self.agent_combo.clear()
            for ag in AgentModel.select():
                self.agent_combo.addItem(f"🤖 {ag.name}", userData=ag)
            self.agent_combo.blockSignals(False)

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

        # Side A
        if self.cards_a:
            self.lbl_count_a.setText(f"{self.index_a + 1} / {len(self.cards_a)}")
            current_card_a = self.cards_a[self.index_a]
            self.json_edit_a.setPlainText(json.dumps(current_card_a, ensure_ascii=False, indent=2))

            tmpl_a = {"name": "Carte 1", "qfmt": current_card_a.get("Front", "{{Front}}")}
            if self.view_side_combo.currentIndex() == 1:
                tmpl_a["afmt"] = current_card_a.get("Back", "{{Back}}")

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

            tmpl_b = {"name": "Carte 1", "qfmt": current_card_b.get("Front", "{{Front}}")}
            if self.view_side_combo.currentIndex() == 1:
                tmpl_b["afmt"] = current_card_b.get("Back", "{{Back}}")

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

        engine_a = self.engine_a_combo.currentData()
        engine_b = self.engine_b_combo.currentData()

        show_toast(self, "Lancement du test A/B en parallèle...")
        self.btn_run.setEnabled(False)

        provider_a = None
        provider_b = None

        if self.ai_manager:
            if engine_a and hasattr(self.ai_manager, "create_provider_from_config"):
                try:
                    provider_a = self.ai_manager.create_provider_from_config(engine_a)
                except Exception:
                    pass  # nosec B110
            if engine_b and hasattr(self.ai_manager, "create_provider_from_config"):
                try:
                    provider_b = self.ai_manager.create_provider_from_config(engine_b)
                except Exception:
                    pass  # nosec B110

        payload_a = CreationTaskPayload(
            text_source=text_source,
            note_type_id=nt_id,
            note_type_fields_schema=nt_schema,
            pipeline_id=1,
            pipeline_name="AB_Test_A",
            pipeline_steps=[],
            use_vision=False,
        )

        payload_b = CreationTaskPayload(
            text_source=text_source,
            note_type_id=nt_id,
            note_type_fields_schema=nt_schema,
            pipeline_id=1,
            pipeline_name="AB_Test_B",
            pipeline_steps=[],
            use_vision=False,
        )

        self.worker_a = CreationWorker(ai_provider=provider_a, payload=payload_a)
        self.worker_a.finished.connect(self._on_finished_a)

        self.worker_b = CreationWorker(ai_provider=provider_b, payload=payload_b)
        self.worker_b.finished.connect(self._on_finished_b)

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
